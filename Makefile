.PHONY: setup lint typecheck test test-unit test-integration check api compose-up compose-down sandbox-libs sandbox-up sandbox-down agent-evals

# SHAs pinados dos repos NAO-confiaveis (docs/07) que o Dockerfile do sandbox copia.
GENIE_PIN := a407a2e2
OMNI_PIN  := fe155b81

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

# Clones pinados de Omni/Genie que o Dockerfile do sandbox copia. Sao NAO-confiaveis (docs/07),
# logo NAO versionados aqui: ficam em sandbox/libs/ (gitignored). Idempotente — clona so se
# faltar e sempre fixa no SHA pinado (fetch-by-sha de fallback p/ commit fora do default branch).
sandbox-libs:
	@test -d sandbox/libs/genie/.git || git clone https://github.com/automagik-dev/genie sandbox/libs/genie
	@git -C sandbox/libs/genie checkout --quiet $(GENIE_PIN) 2>/dev/null || ( git -C sandbox/libs/genie fetch --quiet origin $(GENIE_PIN) && git -C sandbox/libs/genie checkout --quiet $(GENIE_PIN) )
	@test -d sandbox/libs/omni/.git || git clone https://github.com/namastexlabs/omni sandbox/libs/omni
	@git -C sandbox/libs/omni checkout --quiet $(OMNI_PIN) 2>/dev/null || ( git -C sandbox/libs/omni fetch --quiet origin $(OMNI_PIN) && git -C sandbox/libs/omni checkout --quiet $(OMNI_PIN) )
	@echo ">> sandbox/libs vendorizado (genie@$(GENIE_PIN), omni@$(OMNI_PIN))"

# Sandbox isolada do agente (Omni/Genie/Claude Code) — zona NAO-confiavel (docs/07, ADR-0006),
# por isso FORA do `compose-up` padrao. Parte DETERMINISTICA: vendoriza os clones pinados
# (sandbox-libs) + builda as 2 imagens + sobe o overlay isolado.
# Os passos INTERATIVOS (claude login, pareamento WhatsApp) seguem o sandbox/RUNBOOK.md.
sandbox-up: sandbox-libs
	docker build -f sandbox/Dockerfile -t khal-sandbox:base .
	docker build -t khal-egress-proxy sandbox/egress
	docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml up -d --force-recreate mcp-server egress-proxy sandbox
	@echo ">> sandbox no ar. Proximo (interativo): docker exec -it khal-sandbox claude login — ver sandbox/RUNBOOK.md"

sandbox-down:
	docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml down

# Eval ao vivo do agente: dirige `claude -p` (sem key, ADR-0007) contra o /mcp.
# Requer o stack no ar (make compose-up) e o Claude Code autenticado.
agent-evals:
	uv run python -m src.evals.run
