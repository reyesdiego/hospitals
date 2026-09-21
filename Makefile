.PHONY: db-up db-down install run migrate migration seed-users seed-practices seed-diagnoses migrate-treatment-schedules inherit-waiting-periods test lint

# Con uv instalado los comandos corren en el entorno del proyecto sin activarlo; sin uv,
# se usa lo que haya en el PATH, que es el venv activado a mano.
RUN := $(shell command -v uv >/dev/null 2>&1 && echo "uv run --")

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

install:
	python -m pip install -e ".[dev]"

run:
	$(RUN) uvicorn app.main:app --reload

migrate:
	$(RUN) alembic upgrade head

migration:
	$(RUN) alembic revision --autogenerate -m "$(m)"

seed-users:
	$(RUN) python -m app.db.seeds.users

seed-practices:
	$(RUN) python -m app.db.seeds.practices $(ARGS)

seed-diagnoses:
	$(RUN) python -m app.db.seeds.diagnoses $(ARGS)

test:
	$(RUN) pytest

lint:
	$(RUN) ruff check .

migrate-treatment-schedules:
	$(RUN) python -m app.db.maintenance.treatment_schedules $(ARGS)

inherit-waiting-periods:
	$(RUN) python -m app.db.maintenance.waiting_periods $(ARGS)
