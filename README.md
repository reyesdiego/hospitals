# Hospital API

Starter modular de FastAPI + SQLAlchemy async + PostgreSQL + Alembic.

## Inicio

```bash
cp .env.example .env
docker compose up -d postgres
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- PostgreSQL local: `localhost:5434`

## Actualizar cliente Orval

El frontend genera sus tipos y cliente HTTP desde el OpenAPI vivo de FastAPI:
`http://localhost:8000/openapi.json`.

1. Levantar la API:

```bash
uvicorn app.main:app --reload
```

2. Regenerar el cliente:

```bash
cd frontend
npm run generate:api
```

Ejecuta este flujo cada vez que cambies rutas, schemas o responses de FastAPI.

## Frontend

```bash
cd frontend
npm run dev                          # contra la API real (http://localhost:8000)
VITE_USE_MOCK_API=true npm run dev   # con el adaptador mock, sin backend
```

- `src/pages/HospitalizationDetailPage.tsx` orquesta el ciclo de la internación con las
  tarjetas de `src/components/hospitalization/` (ciclo, cama, alta, servicio responsable,
  equipo asistencial y auditoría).
- `src/pages/MedicalPracticesPage.tsx` es el catálogo de prácticas: filtros por
  nomenclador y capítulo, unidades de cada práctica y valores por financiador.
- `src/components/hospitalization/PracticesCard.tsx` registra las prácticas de la
  internación, quién las recetó y el importe que cargaron a la cuenta.
- `src/components/hospitalization/AccountCard.tsx` muestra la cuenta con sus cargos y
  permite anularlos indicando el motivo.
- `src/pages/BedsPage.tsx` es el tablero de camas: ocupación, reserva con vencimiento,
  limpieza, estado operativo e historial de estados.
- El adaptador mock (`src/api/mock-db.ts` + `src/api/mock-workflow.ts` +
  `src/api/mock-practices.ts`) replica las reglas del backend, incluidos los conflictos
  409, para poder trabajar sin base de datos.

## Módulos

- Pacientes (identificadores externos y contactos)
- Coberturas (financiadores, planes y cobertura del paciente)
- Admisión (solicitud de internación, consentimientos y autorizaciones)
- Instituciones, habitaciones y camas
- Internaciones (servicio responsable, equipo asistencial)
- Camas: búsqueda, reserva con vencimiento, ocupación, traslado, limpieza e historial de estados
- Alta: planificación, alta clínica, salida física y alta administrativa
- Cuenta de internación con ítems de cargo y anulación de cargos
- Auditoría de eventos de la internación
- Prácticas médicas: catálogo del nomenclador y valores acordados por financiador
- Prácticas de la internación: qué se indicó, qué profesional lo recetó y el cargo que
  generó cada práctica realizada

## Prácticas médicas

El catálogo sigue la forma en la que se nomenclan las prácticas en Argentina: cada
práctica pertenece a un nomenclador (`NACIONAL`, `NBU`, `NU_SSS`, `HPGD` o `PROPIO`), a un
capítulo y a un ámbito (ambulatorio, internación o ambos), y lleva las unidades que el
nomenclador le asigna: galeno (honorarios), gastos, anestesia, bioquímicas (UB) y
radiológicas (UR). El código es único dentro de su nomenclador, no entre nomencladores.

Las unidades son una cosa y el dinero es otra: el valor vive en `medical_practice_tariffs`,
por financiador, por plan y con vigencia. Si se informa el valor de la unidad, los
honorarios y los gastos se calculan con las unidades de la práctica; también puede
pactarse un importe cerrado. El coseguro queda registrado en el mismo valor.

`GET /api/v1/practices/{id}/tariffs/effective` resuelve el valor que corresponde a una
cobertura en una fecha: primero el del plan, después el del financiador y por último el
institucional (el de `payer_id` vacío, que es el del paciente particular).

### Prácticas de la internación

`hospitalization_practices` registra cada práctica indicada en una internación junto con
el profesional que la recetó (`prescribed_by_id`, obligatorio) y, si corresponde, el que
la realizó. Indicar y realizar son momentos distintos:

```
práctica indicada (REQUESTED) → realizada (PERFORMED) → cargo en la cuenta
                              ↘ anulada (CANCELLED, solo si todavía no se realizó)
```

La realización es la que genera el cargo: `charge_items` guarda `practice_id` y el código
del nomenclador, el precio sale del valor vigente de la práctica para la cobertura de la
internación a la fecha de realización, y la categoría del cargo se deriva del tipo de
práctica (consulta → honorarios, laboratorio → laboratorio, cirugía → procedimiento…).
El importe puede informarse a mano cuando la práctica no tiene valor acordado.

- una práctica realizada con cargo activo no se anula ni se vuelve a facturar: primero se
  anula el cargo en la cuenta;
- el código y el nombre de la práctica se copian al registro, para que editar el
  nomenclador no reescriba la historia de la internación;
- la cuenta cerrada rechaza cargos nuevos, así que tampoco acepta prácticas realizadas;
- cada paso queda en la auditoría: `PRACTICE_ORDERED`, `PRACTICE_PERFORMED` y
  `PRACTICE_CANCELLED`.

### Anulación de cargos

`POST /api/v1/hospitalizations/{id}/account/charge-items/{charge_item_id}/void` anula un
cargo. El cargo **no se borra**: queda en la cuenta con `status = VOID`, motivo, fecha y
responsable, deja de sumar a `total_amount` y pasa a `voided_amount`. Anular dos veces es
inofensivo y una cuenta cerrada no acepta anulaciones.

Eso cierra el circuito con las prácticas: una vez anulado el cargo, la práctica realizada
puede volver a facturarse (`/perform` con el importe correcto, que genera un cargo nuevo) o
anularse. La anulación también queda en la auditoría como `CHARGE_ITEM_VOIDED`.

## Flujo de internación

Cada momento del proceso es un evento distinto y se registra por separado:

```
Solicitud de admisión → autorización → internación → servicio responsable
→ reserva de cama → ocupación (ingreso) → traslados
→ prácticas indicadas y realizadas (cargos)
→ planificación del alta → alta clínica → salida física → alta administrativa
→ cuenta lista para auditoría → cierre financiero
```

Diferencias que el modelo mantiene explícitas:

- El alta clínica **no** libera la cama: la cama sigue `OCCUPIED` y la asignación activa.
- La salida física termina la asignación y deja la cama en `PENDING_CLEANING`.
- El alta administrativa cierra las relaciones históricas abiertas y entrega la cuenta.
- El cierre financiero es independiente y es el que cierra la internación.

Ciclo de la cama:

```
AVAILABLE → RESERVED → OCCUPIED → PENDING_CLEANING → CLEANING → AVAILABLE
```

### Integridad y concurrencia

La base de datos es la última barrera:

- índice único parcial: una sola asignación activa por cama y por internación;
- índice único parcial: una sola reserva activa por cama y por internación;
- un solo servicio responsable activo, un solo médico de cabecera activo y un solo plan
  de alta activo por internación;
- índice único con `NULLS NOT DISTINCT`: un solo valor por práctica, financiador, plan y
  fecha de inicio, de modo que el valor institucional (sin financiador) tampoco se puede
  cargar dos veces.

Las operaciones sobre camas (reservar, ocupar, trasladar, liberar) bloquean las filas
involucradas con `SELECT ... FOR UPDATE` dentro de una única transacción del servicio, y
los conflictos de base de datos se traducen a errores de dominio (HTTP 409).

## Tests

```bash
pytest
```

Las pruebas de integración usan una base propia (`<POSTGRES_DB>_test`, configurable con
`HOSPITAL_TEST_DB`) y se omiten automáticamente si PostgreSQL no está disponible.
