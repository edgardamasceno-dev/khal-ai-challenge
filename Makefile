.PHONY: setup lint typecheck test test-unit test-integration check api compose-up compose-down

setup:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest

test-unit:
	pytest tests/unit tests/api

test-integration:
	pytest tests/integration

check: lint typecheck test

api:
	uvicorn src.interfaces.rest.app:app --reload

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down
