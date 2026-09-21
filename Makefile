.PHONY: db-up db-down install run migrate migration seed-users seed-practices seed-diagnoses inherit-waiting-periods test lint

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

install:
	python -m pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(m)"

seed-users:
	python -m app.db.seeds.users

seed-practices:
	python -m app.db.seeds.practices $(ARGS)

seed-diagnoses:
	python -m app.db.seeds.diagnoses $(ARGS)

test:
	pytest

lint:
	ruff check .

inherit-waiting-periods:
	python -m app.db.maintenance.waiting_periods $(ARGS)
