.PHONY: db-up db-down install run migrate migration seed-practices test lint

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

seed-practices:
	python -m app.db.seeds.practices $(ARGS)

test:
	pytest

lint:
	ruff check .
