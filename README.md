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
python -m app.db.seeds.users     # usuarios iniciales, uno por rol
uvicorn app.main:app --reload
```

- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- PostgreSQL local: `localhost:5434`

## Usuarios y permisos

Todos los endpoints piden sesión salvo `/health` y `/api/v1/auth/login`. El login devuelve
un token opaco (`Authorization: Bearer <token>`, 12 horas) y los permisos del usuario.

`python -m app.db.seeds.users` crea uno por rol con la contraseña `Hospital.2026`, que hay
que cambiar apenas se entra. No pisa usuarios ya creados.

| Usuario | Rol | Puede |
| --- | --- | --- |
| `admin@hospital.local` | Administración | todo, incluido modificar una internación con alta médica y administrar usuarios |
| `recepcion@hospital.local` | Recepción | registrar pacientes y coberturas, admitir, alta administrativa |
| `medico@hospital.local` | Profesional médico | prácticas, equipo asistencial, plan y alta médica |
| `enfermeria@hospital.local` | Enfermería | aplicar las tareas indicadas al paciente, limpieza y estado de camas |

Consultar (`GET`) está habilitado para cualquier usuario con sesión; los permisos gobiernan
lo que modifica datos. Qué permiso pide cada operación está en una tabla única,
`app/core/authorization.py`: lo que no figura ahí y escribe queda solo para administración,
para que agregar un endpoint y olvidarse de la tabla falle cerrado.

Las contraseñas se guardan con `scrypt` y sal por usuario; de las sesiones se guarda solo el
hash del token. Cambiar el rol, dar de baja o cambiar la contraseña de un usuario cierra sus
sesiones abiertas.

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

## Tareas de enfermería

Inyectables, medicación, extracciones y colocación de Holter no son un circuito aparte: son
prácticas del nomenclador marcadas con `is_nursing_task`. El médico las indica desde la
internación como cualquier otra práctica y quedan pendientes; enfermería las ejecuta desde
`GET /nursing-tasks`, que lista lo indicado en internaciones activas con el paciente, la sala
y la cama.

- `POST /nursing-tasks/{order_id}/perform` marca la tarea como aplicada: es la realización de
  siempre, con su cargo en la cuenta y su evento en la internación.
- `POST /nursing-tasks/{order_id}/cancel` la cancela con el motivo.
- `?pending_only=false&on=YYYY-MM-DD` agrega lo aplicado y cancelado ese día, para cerrar turno.

Por este camino solo pasan prácticas marcadas como de enfermería; el resto se registra desde
la internación, que es donde está quien las hace.

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
