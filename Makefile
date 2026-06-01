.PHONY: setup lint typecheck test test-unit test-integration check api compose-up compose-down sandbox-libs sandbox-up sandbox-login sandbox-serve sandbox-smoke sandbox-wanet sandbox-pair sandbox-connect sandbox-media-on sandbox-media-off sandbox-down agent-evals

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
	@docker network create khal-wanet >/dev/null 2>&1 || true
	docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml up -d --build --force-recreate mcp-server egress-proxy sandbox backend notifications-worker
	@echo ">> sandbox no ar; backend/worker wired ao Omni (khal-wanet) p/ resolução LID + proativo (SPEC-030)."
	@echo ">> Fluxo: make sandbox-login -> make sandbox-serve -> make sandbox-smoke (ver sandbox/RUNBOOK.md)"

# Etapa 2 (RUNBOOK): login INTERATIVO do Claude Code dentro do sandbox (device-flow,
# persiste no volume claude-home — ADR-0007). Rode no SEU terminal. Idempotente.
sandbox-login:
	docker exec -it khal-sandbox claude login

# Etapas 3+4 (RUNBOOK): wiring do agente CX (tool-scoping + MCP) + daemons do sandbox
# (Postgres-genie + NATS/JetStream + Omni API + genie serve), tudo DETERMINISTICO. Roda UMA
# vez sobre um sandbox recem-subido (make sandbox-up). Pre-req: make sandbox-login. Espera o
# "genie serve is running" e falha (exit 1) se nao subir em 120s.
sandbox-serve:
	docker exec -d khal-sandbox sh -c 'bash /srv/sandbox-up.sh > /tmp/up.log 2>&1'
	@docker exec khal-sandbox sh -c 'for i in $$(seq 1 120); do grep -q "genie serve is running" /tmp/up.log 2>/dev/null && break; sleep 1; done; \
	  if grep -q "genie serve is running" /tmp/up.log; then echo ">> daemons no ar (genie serve running). E2E interno: make sandbox-smoke"; \
	  else echo "FALHA: genie serve nao subiu em 120s"; tail -25 /tmp/up.log; exit 1; fi'

# Etapa 5 (RUNBOOK): E2E interno SEM WhatsApp. Publica uma omni.message sintetica de uma
# persona do seed e PROVA a malha NATS -> bridge -> spawn do agente -> tool-calls no MCP.
# Self-test reproduzivel (exit != 0 se a malha nao fechar). A entrega real e a Etapa 6.
sandbox-smoke:
	bash sandbox/smoke.sh

# Etapa 6.0 (RUNBOOK): a PARTE DETERMINISTICA do E2E WhatsApp real. Conecta o sandbox a uma
# rede NAO-interna (khal-wanet) p/ o WSS direto do Baileys (que nao honra HTTP_PROXY). Mantem
# backend/database INALCANCAVEIS (so-MCP) — abre mao do egress allowlist SO p/ o omni/Baileys.
# O resto da Etapa 6 (omni auth, criar instancia, PAREAR — 2 celulares) e interativo: RUNBOOK §6.
sandbox-wanet:
	@docker network create khal-wanet >/dev/null 2>&1 || true
	@docker network connect khal-wanet khal-sandbox 2>/dev/null || true
	@docker exec khal-sandbox sh -c 'curl -s -o /dev/null -w ">> web.whatsapp.com -> %{http_code} (espera 200/4xx = alcanca)\n" --noproxy "*" --max-time 8 https://web.whatsapp.com; \
	  curl -s -o /dev/null -w ">> backend          -> %{http_code} (espera 000 = bloqueado)\n" --noproxy "*" --max-time 4 http://backend:8000/health; \
	  curl -s -o /dev/null -w ">> database         -> %{http_code} (espera 000 = bloqueado)\n" --noproxy "*" --max-time 4 http://database:5432' || true
	@echo ">> sandbox na khal-wanet. Proximo: make sandbox-pair PHONE=+<DDI><numero-do-bot>"

# Etapas 6.1+6.2 (RUNBOOK): omni auth + cria/reusa a instancia + conecta + gera o PAIRING
# CODE p/ o numero do bot (a unica acao fisica e digitar o codigo no celular do bot).
# Uso: make sandbox-pair PHONE=+16472015092
sandbox-pair:
	@bash sandbox/pair.sh "$(PHONE)"

# Etapa 6.3 (RUNBOOK): liga a instancia pareada ao agente luz-do-vale (omni connect).
sandbox-connect:
	@bash sandbox/connect.sh

# Etapa 6.6 (RUNBOOK): OPT-IN do anexo de PDF (SPEC-019/ADR-0010). Conecta a rede `bridge`
# (saida NAT) p/ o upload do Baileys aos CDNs de midia — o link presigned e localhost (so
# alcancavel local/WhatsApp Web), entao o ANEXO e o caminho de entrega no demo. Default =
# isolado (so o link). sandbox-media-off restaura o isolamento.
sandbox-media-on:
	@bash sandbox/enable-media.sh
sandbox-media-off:
	@bash sandbox/disable-media.sh

sandbox-down:
	docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml down

# Eval ao vivo do agente: dirige `claude -p` (sem key, ADR-0007) contra o /mcp.
# Requer o stack no ar (make compose-up) e o Claude Code autenticado.
agent-evals:
	uv run python -m src.evals.run
