# khal-ai-challenge

[![CI](https://github.com/edgardamasceno-dev/khal-ai-challenge/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/edgardamasceno-dev/khal-ai-challenge/actions/workflows/ci.yml)

Agente conversacional de CX para uma **distribuidora de energia** ficticia, atendendo no **WhatsApp**. O canal e o **Omni** (Baileys), a orquestracao e o **Genie** (Claude Code), e as ferramentas de negocio sao expostas por um **MCP server em Python**.

> Status: scaffolding. O comportamento de produto e entregue por SPEC, com TDD, conforme `docs/specs/` e o fluxo de engenharia do contexto.

## O que o agente resolve

Atendimento de uma utility de energia: segunda via de fatura (com PDF no WhatsApp), status de interrupcao (outage), abertura de chamado com protocolo, consulta de SLA, base de conhecimento e handoff humano. Notificacoes proativas de outage e baixa de pagamento sao disparadas pelo console do operador.

## Arquitetura (resumo)

```mermaid
flowchart LR
    U["Cliente WhatsApp"] --> O["Omni / Baileys"]
    O --> N["NATS"] --> G["Genie / Claude Code"]
    G -->|MCP HTTP/SSE| M["MCP server (Python)"]
    M --> APP["Application (DDD)"]
    APP --> DB["PostgreSQL"]
    APP --> PDF["WeasyPrint"]
    UI["Console operador (React/Shadcn)"] --> REST["FastAPI"] --> APP
    M -->|send/media: PDF| O
    G -->|reply texto| O --> U
```

Detalhe e trade-offs em `docs/adrs/` e no contexto `../docs/09-stack-khal-ai-challenge.md`.

## Camadas

- **Sistema legado simulado**: FastAPI REST + PostgreSQL + console React (dono dos dados e acoes).
- **Integracao do agente**: MCP server que expoe ferramentas tipadas (Pydantic) com guardrails.

## Setup rapido

```bash
cp .env.example .env   # ajuste SEED_PERSONAS (numeros de demo) e credenciais
make compose-up        # database + seed (one-shot) + backend + frontend + mcp-server + gateway
```

- **Personas via `SEED_PERSONAS`** (`.env`, SPEC-006): `"Nome:telefone;..."`, de 1 a ~100.
  O serviço `seed` (Python/SQLAlchemy, idempotente) materializa a massa; re-seed do zero:
  `docker compose down -v && make compose-up`.
- **Console do operador** (React/Shadcn) em `http://localhost/` — busque uma persona de
  demo (default: `555199990001` Ana, `555199990002` Carlos, `555199990003` Joana). Ver
  `ui/README.md` e `docs/specs/SPEC-002-operator-console.md`.
- **API legada** em `http://localhost/api` — OpenAPI/Swagger em `http://localhost/api/docs`.
  Contratos: `docs/specs/SPEC-001-legacy-rest-api.md`.
- **Base de conhecimento** (`kb/` markdown) com retrieval léxico em `GET /api/kb/search`;
  alimenta a tool `search_knowledge_base` e a jornada J8. Ver `docs/specs/SPEC-005-knowledge-retrieval.md`.
- **MCP server** (ferramentas do agente) em `http://localhost/mcp` — streamable-HTTP, consome
  a API legada com guardrails determinISticos. Ver `docs/specs/SPEC-003-mcp-server.md`.
  Plugue no Claude Code: `claude mcp add --transport http luz-do-vale http://localhost/mcp`.
- **Fatura em PDF** (`generate_invoice_pdf`): render realista A4 (PIX QR + boleto + juros)
  via WeasyPrint, persistido no **MinIO** e servido em `http://localhost/files/...` (proxy do
  gateway); `?presigned=true` devolve link com expiração. Ver `docs/specs/SPEC-008-invoice-pdf.md`.
- **Notificações proativas** (`/api/proactive`): o operador dispara, pelo console, "baixa de
  pagamento" / "status de interrupção" → evento `utilitycx.*` no **NATS** → **worker
  determinístico** (sem LLM) envia a mensagem canônica via Omni e grava em
  `conversation_memory`. Ver `docs/specs/SPEC-009-proactive-notifications.md` (ADR-0005).
- **Agente CX** em `agent/AGENTS.md` (+ `agent/mcp.config.json`) — papel, política e guardrails
  que orquestram as tools do `/mcp`. Avaliação ao vivo (dirige `claude -p`, sem key — ADR-0007):
  `make agent-evals` (requer o stack no ar + Claude Code autenticado). Ver `docs/specs/SPEC-004-agent-cx.md`.

Increments seguintes (WhatsApp via Omni/Genie no sandbox) seguem o rollout do ADR-0006.

## Qualidade

Testes em Python 3.12 (unit + api dispensam banco; integration usa Postgres efemero):

```bash
make test-unit          # dominio + use cases + API (repositorios fake)
make test-integration   # repositorios contra Postgres (DATABASE_URL)
make check              # ruff + mypy + suite completa
```

### Integracao continua (GitHub Actions)

`/.github/workflows/ci.yml` roda em `push`/`pull_request` para `develop` e nas branches de
entrega. Dois jobs:

- **`quality`** (sempre, inclusive em forks sem segredo): sobe um Postgres de servico, aplica
  o schema e executa `uv sync` -> `ruff` -> `mypy` -> `pytest` (unit/api/integration). Inclui o
  teste de **paridade da allowlist** (impede o drift do PDF/contexto entre server, frontmatter
  e evals).
- **`eval-gate`** (condicional ao segredo `ANTHROPIC_API_KEY`): dirige o agente headless contra
  o `/mcp` e calcula um **score 0-100** (`round(100 * PASS / TOTAL)`); o **gate >= 85** reprova
  o merge. Sem o segredo (ex.: PR de fork) o job e **pulado** (skip), nao falha. Limiar
  configuravel por `EVAL_GATE_MIN` (default 85).

A tool de memoria `get_conversation_context` (read-only, ADR-0005) deixa o agente ler o
historico canonico do titular no abrir da conversa (jornada concierge: boas-vindas proativo +
recuperacao empatica de cliente nao identificado, AGENTS.md). Ver `docs/specs/SPEC-022-conversation-context.md`
e `docs/specs/SPEC-023-journey-resilience.md`.

## Mapa de documentos

- `docs/domain/` - linguagem ubiqua, modelo de dominio, dicionario de dados, ERD, personas, seed.
- `docs/adrs/` - decisoes arquiteturais.
- `docs/specs/` - especificacoes por feature (TDD).
- `docs/testing/` - estrategia de testes e rubrica de evals.
- `docs/security/` - threat model e tratamento de PII.
- `docs/operations/` - runbook e roteiro de demo.
- `agent/AGENTS.md` - papel, politica e ferramentas do agente.
- `kb/` - base de conhecimento (corpus de retrieval).

## Seguranca

Dados ficticios, sem PII real. Numeros de WhatsApp vem do `.env` (nunca commitados). Omni/Genie executam apenas em sandbox. Ver `docs/security/`.
