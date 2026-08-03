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

## Módulos iniciales

- Pacientes
- Instituciones
- Camas
- Internaciones
- Asignación y liberación transaccional de camas

La asignación bloquea las filas de internación y cama, y la base agrega índices únicos
parciales para impedir dos asignaciones activas sobre una cama o internación.
