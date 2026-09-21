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
python -m app.db.seeds.users       # usuarios iniciales, uno por rol
python -m app.db.seeds.diagnoses   # catálogo CIE-10
uvicorn app.main:app --reload
```

Con [uv](https://docs.astral.sh/uv/) instalado, los targets del `Makefile` corren en el
entorno del proyecto sin activarlo: `make db-up`, `make migrate`, `make seed-users`,
`make run`, `make test`, `make lint`.

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
| `enfermeria@hospital.local` | Enfermería | aplicar las tareas indicadas al paciente, registrar las tomas de medicación, limpieza y estado de camas |

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
npm run dev   # contra la API en http://localhost:8000
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
- `src/components/hospitalization/TreatmentsCard.tsx` y `ClinicalNotesCard.tsx` registran
  la medicación en curso y las evoluciones, observaciones e interconsultas.
- `src/components/nursing/MedicationTimeline.tsx` es la línea de tiempo de la vuelta de
  medicación en el panel de enfermería.
- `src/pages/BedsPage.tsx` es el tablero de camas: ocupación, reserva con vencimiento,
  limpieza, estado operativo e historial de estados.
- `src/pages/DiagnosesPage.tsx` es el catálogo CIE-10 y `src/pages/MorbidityReportPage.tsx`
  el informe estadístico de egresos por diagnóstico.
- `src/pages/PatientRecordPage.tsx` es la historia clínica del paciente, con todo lo suyo
  en una pantalla.

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
- Diagnósticos: catálogo CIE-10 y los diagnósticos de ingreso y de egreso del paciente
- Medicación y tratamiento de la internación, con su registro de administración
- Evoluciones, observaciones e interconsultas
- Pagos del paciente y saldo de la cuenta
- Resumen de alta, historia clínica del paciente e informe estadístico de morbilidad

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

### Quién paga cada cargo, y los pagos del paciente

Cada cargo dice a cargo de quién está (`responsible_party`): con cobertura detrás se le
factura al financiador y sin cobertura lo paga el paciente, que es particular. Los copagos
de la cartilla son siempre del afiliado, aunque la cuenta tenga cobertura.

`POST /api/v1/hospitalizations/{id}/account/payments` registra un cobro con su importe,
medio, comprobante y quién cobró. No se puede cobrar más de lo que el paciente debe: si el
importe supera el saldo, primero hay que agregar el cargo que falta. Un pago mal cargado se
anula con su motivo y el importe vuelve a quedar adeudado; el recibo ya salió y la caja del
día tiene que poder explicarse.

**El alta administrativa no sale con saldo del paciente pendiente.** Una vez dada, el
paciente ya no es del hospital y cobrarle lo que puso de su bolsillo es correrlo por la
calle. Lo que se le factura al financiador no traba nada: eso se cobra después por convenio.

## Diagnósticos CIE-10

`diagnosis_codes` es la clasificación completa en español —21 capítulos, 209 grupos, 1.634
categorías y 12.634 subcategorías— que se carga con `python -m app.db.seeds.diagnoses`
desde `app/db/seeds/cie10.csv`. La carga es idempotente y no pisa lo que la institución
haya desactivado o anotado.

Capítulos y grupos ordenan la lista pero no son diagnósticos: al paciente se le asienta una
categoría o una subcategoría. Son más de catorce mil códigos, así que `GET /api/v1/diagnoses`
se busca (`search` por código o texto) y responde acotado por `limit`.

La pantalla lo muestra como el árbol que es —capítulo → grupo → categoría → subcategoría—,
pidiendo cada rama al desplegarla; `parent_code` trae los hijos de un código y `child_count`
dice cuántos cuelgan, para no ofrecer ramas vacías. Buscar o filtrar por nivel sale del
árbol y devuelve la lista de coincidencias, que es lo que se quiere ver al buscar.

`hospitalization_diagnoses` es el diagnóstico del paciente, y distingue dos momentos que
conviven: el **de ingreso**, presuntivo, que se carga con la admisión, y el **de egreso**,
que es el que firma el médico con el alta. La diferencia entre lo que se sospechó y lo que
resultó es parte de la historia.

- cada diagnóstico tiene un rol: principal, secundario, comorbilidad o complicación, y hay
  un solo principal por momento (índice único parcial);
- el código y el texto se copian del catálogo al asentarlo: la clasificación se edita y la
  historia tiene que leerse igual dentro de diez años;
- un código dado de baja o que no sea codificable se rechaza.

## Medicación, tratamiento y evolución

Las prácticas son cargos puntuales; esto es lo otro que ocupa el día de una sala.

`hospitalization_treatments` es lo que el paciente **recibe**: droga o tratamiento
—kinesiología, oxígeno, dieta—, con presentación, dosis, vía y frecuencia. Es un plan que
empieza y termina: `ACTIVE → SUSPENDED | COMPLETED`, siempre con fecha y motivo. Una
indicación cerrada no se edita: se indica de nuevo.

La frecuencia es estructurada, que es lo que permite calcular horarios:

| Esquema | Qué significa | Cómo se calcula la próxima |
| --- | --- | --- |
| `INTERVAL` | cada N horas | desde la última toma dada: un atraso corre las siguientes |
| `TIMES` | horarios fijos del día | los horarios no se mueven: la de las 14 que no se dio queda vencida |
| `ONCE` | una sola vez | al inicio, y desaparece cuando se da |
| `AS_NEEDED` | a demanda | no se vence |
| `CONTINUOUS` | goteo, oxígeno | no se da por tomas |

El texto de la frecuencia se escribe solo desde el esquema ("cada 8 horas", "08:00 - 20:00")
para no tener dos verdades. El cálculo de horarios vive en `app/services/medication_schedule.py`,
separado de la base porque es la parte que hay que poder razonar: se prueba sin PostgreSQL.

`hospitalization_notes` es lo que se escribe: evolución diaria, observación, interconsulta
—la atención de un médico de otra especialidad, con su servicio— o nota de enfermería.
Guarda el profesional que atendió y, aparte, el usuario que la cargó. Una nota cargada por
error se anula con su motivo y el texto queda: la historia clínica se corrige agregando.

Las dos respetan el candado posterior al alta médica: con el alta dada solo escribe un
administrador, y queda asentado en el historial de la internación.

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

### Registro de administración y línea de tiempo

La indicación dice lo que hay que hacer; el registro de administración dice lo que pasó.
`POST /hospitalizations/{id}/treatments/{treatment_id}/administrations` deja constancia de
cada toma: la hora, la dosis —la de la indicación si no se aclara otra—, la vía, el
profesional que la aplicó y el usuario que la cargó.

- una toma que no se pudo dar se registra **omitida y con su motivo**: el ayuno, el rechazo
  o el paciente que no estaba en la cama también son información clínica;
- una toma cargada por error se anula: deja de contar y el horario vuelve a quedar vencido;
- una indicación suspendida acepta la toma que quedó sin cargar antes del corte —la
  enfermera carga al final del turno lo que dio hace dos horas— y rechaza las posteriores.

`GET /nursing-medications` es la vuelta de medicación: las indicaciones activas de las
internaciones activas con el paciente, la cama y el servicio, y para cada una la línea de
tiempo de la ventana pedida —lo dado, lo omitido, lo que falta y lo vencido—, el próximo
horario y si se pasó de hora. Sin ventana son las doce horas para atrás y las doce para
adelante; primero lo vencido. Hay media hora de tolerancia antes de marcar algo vencido,
que es lo que tarda una vuelta de sala.

El panel de enfermería lo muestra como una línea de tiempo: una fila por indicación y cada
toma ubicada en su hora.

## Indicaciones del alta

Al dar el alta médica el profesional escribe lo que el paciente se lleva: medicación
(`MEDICATION`, texto libre porque el vademécum no vive acá) y prácticas para hacerse
(`PRACTICE`, elegidas del nomenclador o escritas a mano), en
`/hospitalizations/{id}/discharge-prescriptions`.

`GET .../discharge-prescriptions/pdf` devuelve el documento para imprimir: dos hojas, la
receta y la indicación de prácticas, cada una con paciente, cobertura, profesional que firma
y fecha de alta.

Son la excepción al candado posterior al alta médica: se escriben justamente en ese momento,
así que se pueden cargar y corregir hasta el egreso administrativo, cuando la internación
queda cerrada.

## Resumen de alta

`GET /api/v1/hospitalizations/{id}/discharge-summary/pdf` es la epicrisis: el documento que
cierra la internación y el que lee el médico que recibe al paciente después. Trae el motivo
de internación, los diagnósticos CIE-10 de ingreso y de egreso, las prácticas realizadas, la
medicación y los tratamientos con las tomas que efectivamente se registraron, las
evoluciones e interconsultas, el egreso y la medicación al alta.

Se arma con lo que ya está cargado; no se escribe aparte, porque un resumen que se escribe
dos veces termina diciendo dos cosas distintas. Sin alta médica sale igual, marcado como
documento provisorio.

## Historia clínica del paciente

`GET /api/v1/patients/{id}/record` da vuelta el modelo: el sistema trabaja por internación
y esto mira por paciente, que es lo que necesita el médico que lo atiende hoy. En una sola
respuesta trae sus internaciones con la ubicación y el diagnóstico que mejor las explica,
los diagnósticos, las prácticas —con las consultas separadas del resto—, la medicación, las
notas, las recetas del alta, los pagos y los totales de plata a su cargo, cobrada y
adeudada.

## Informe estadístico de morbilidad

`GET /api/v1/reports/morbidity` cuenta los egresos del período por diagnóstico, que es lo
que pide cualquier informe hacia afuera. Por omisión, por el diagnóstico principal de
egreso; se puede pedir por los de ingreso, por otro rol o sin filtrar rol, y agrupado por
código o por capítulo. Cada fila trae egresos, pacientes distintos, estadía promedio,
fallecidos y mortalidad.

Se cuenta sobre los egresos: una internación en curso no tiene diagnóstico definitivo. Los
egresos que nadie codificó se informan aparte en lugar de desaparecer, porque un informe
que no dice lo que le falta se lee como si estuviera completo.

## Autorización de la cobertura

La admisión valida contra el financiador el código de autorización que trae el afiliado y
muestra el copago que queda a cargo del paciente, o el valor particular de la práctica
cuando la cobertura no la autoriza.

Mientras no exista la integración real, `POST /api/v1/payer-mock/authorizations` hace de
prestadora: valida un código de 3 dígitos con reglas deterministas —`000` no figura, último
dígito impar se rechaza, par se autoriza— y resuelve el resto contra datos reales del
sistema, la cartilla del plan y el tarifario. **Es un mock**: el módulo lo dice y el circuito
de admisión está listo para cambiarlo por el API del financiador.

## Flujo de internación

Cada momento del proceso es un evento distinto y se registra por separado:

```
Solicitud de admisión → autorización → internación → servicio responsable
→ reserva de cama → ocupación (ingreso) → traslados
→ diagnósticos de ingreso
→ prácticas indicadas y realizadas (cargos)
→ medicación y tratamiento, con sus tomas
→ evoluciones e interconsultas
→ planificación del alta → alta clínica (diagnósticos de egreso) → salida física
→ pagos del paciente → alta administrativa
→ cuenta lista para auditoría → cierre financiero
```

Diferencias que el modelo mantiene explícitas:

- El alta clínica **no** libera la cama: la cama sigue `OCCUPIED` y la asignación activa.
- La salida física termina la asignación y deja la cama en `PENDING_CLEANING`.
- El alta administrativa cierra las relaciones históricas abiertas y entrega la cuenta, y
  no sale mientras el paciente tenga saldo a su cargo.
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

## Seeds y mantenimiento

```bash
make seed-users                                    # un usuario por rol
make seed-practices ARGS="--unit-value 850"        # nomenclador, con valor institucional
make seed-diagnoses                                # catálogo CIE-10
make migrate-treatment-schedules                   # frecuencia escrita a mano → esquema
make inherit-waiting-periods                       # carencias pactadas → las de la práctica
```

Los seeds son idempotentes: el código es la identidad, lo desconocido se inserta, lo
conocido se actualiza y nada se borra. Los scripts de mantenimiento no escriben sin
`ARGS=--apply`: primero informan qué cambiarían.

`migrate-treatment-schedules` lee la frecuencia en texto de las indicaciones cargadas antes
del esquema estructurado ("cada 8 horas", "08:00 y 20:00", "SOS") y la completa cuando la
entiende. Lo que no entiende lo deja como está y lo informa: es preferible una indicación
sin horarios a una con horarios que nadie indicó.

## Tests

```bash
make test        # o: uv run pytest
```

Las pruebas de integración usan una base propia (`<POSTGRES_DB>_test`, configurable con
`HOSPITAL_TEST_DB`) y se omiten automáticamente si PostgreSQL no está disponible.

Esa base se rehace entera al empezar cada corrida. `create_all` agrega tablas nuevas pero no
columnas ni valores de enum, así que una base vieja hace fallar las pruebas de un modelo que
cambió con un error que no tiene nada que ver con lo que se está probando. Cuesta alrededor
de un segundo; `HOSPITAL_TEST_KEEP_DB=1` saltea el paso para iterar sobre una misma prueba.

Lo que es cálculo y no base de datos se prueba sin PostgreSQL: los horarios de medicación
(`tests/test_medication_schedule.py`) y la lectura de la frecuencia escrita a mano
(`tests/test_treatment_schedule_migration.py`).
