.PHONY: setup lint typecheck test test-unit test-integration check api compose-up compose-down agent-evals

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

# Eval ao vivo do agente: dirige `claude -p` (sem key, ADR-0007) contra o /mcp.
# Requer o stack no ar (make compose-up) e o Claude Code autenticado.
agent-evals:
	uv run python -m src.evals.run
