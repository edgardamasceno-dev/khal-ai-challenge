# khal-ai-challenge

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
make setup          # venv + deps
cp .env.example .env # preencher numeros de demo e chaves (fake em sandbox)
make db-up          # postgres via docker
make seed           # popula dados ficticios (24 meses)
make api            # sobe a API legada
make mcp            # sobe o MCP server
```

Pareamento do WhatsApp (Omni/Genie em sandbox) e troubleshooting em `docs/operations/runbook.md`.

## Qualidade

```bash
make check          # ruff + mypy + pytest
make evals          # Agent Score (rubrica em docs/testing/eval-rubric.md)
```

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
