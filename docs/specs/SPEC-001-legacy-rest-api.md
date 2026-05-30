# SPEC-001 - API REST do sistema legado (Luz do Vale)

- Status: Draft
- Versao alvo: 0.2.0 (ferramentas reais - camada de dados/acoes)
- ADRs: ADR-0001 (Python/Pydantic), ADR-0002 (console consome OpenAPI), ADR-0006 (compose, increment 2)
- Validado antes em POC (`poc/`, MCP-over-REST, gateway por path).

## 1. Problema

O agente precisa de dados e acoes reais do "sistema legado" da distribuidora. Sem uma API REST tipada e testada, nao ha o que o mcp-server consuma (decisao: MCP-over-REST).

## 2. Objetivo

Implementar a API REST legada em arquitetura hexagonal/DDD (Python 3.12 + FastAPI + SQLAlchemy 2.0), sobre o Postgres + seed da SPEC-000, expondo os endpoints que alimentam as ferramentas MCP. Servico `backend` + `gateway` (por path) no compose (increment 2 do ADR-0006).

## 3. Escopo

- Domain: value objects (CPF, Telefone, Dinheiro, MesReferencia, Protocolo, TipoChamado) e entidades por bounded context (Billing, Outage, Ticketing, Conversation).
- Application: ports (Repository/UnitOfWork) + use cases.
- Infrastructure: ORM + repositorios (adapters) sobre o schema existente.
- Interfaces/REST: endpoints, DTOs Pydantic, DI, tratamento de erro.
- Compose: `backend` (FastAPI) + `gateway` (nginx, `/api`) atras do mesmo banco.

Endpoints (cada um alimenta uma tool MCP):
`GET /customers?phone=`, `/customers/{id}`, `/customers/{id}/contracts`, `/customers/{id}/tickets`,
`/units/{id}`, `/units/{id}/invoices`, `/invoices/{id}`, `/invoices/{id}/pdf` (501 reservado),
`GET /outages?bairro=`, `POST /tickets` (idempotente), `GET /tickets/{protocolo}`,
`POST /handoffs`, `GET|PUT /conversations/{chat}/memory`, `GET /health`.

## 4. Fora de escopo

- mcp-server (proxima SPEC), envio de PDF/WeasyPrint + Omni (ADR-0003), KB/retrieval (ADR-0004),
  eventos/worker e console operador (ADR-0005/0002), rede em 2 zonas do ADR-0006.

## 5. Criterios de aceite

- `find_customer_by_phone`: telefone conhecido -> titular; desconhecido -> 404; invalido -> 422.
- `get_invoice_status`: fatura da Ana (2026-05) retorna `em_aberto` com valor e vencimento.
- `get_outage_by_region`: bairro da Ana -> 1 outage ativa; bairro inexistente -> `encontrada=false`.
- `create_ticket`: idempotente por `idempotency_key` (mesma chave -> mesmo protocolo, sem duplicar); tipo invalido -> 422.
- memoria curta: `PUT` faz upsert por `chat_id`+chave (nao duplica); `GET` retorna o valor atual.
- Suite verde (unit + api + integration), ruff e mypy estrito limpos.

## 6. Plano de testes

- Unit: value objects (invariantes) e use cases com repositorios fake em memoria.
- API: FastAPI TestClient com repositorios fake injetados (HTTP -> service -> domain), cobrindo status codes/edge cases.
- Integration: repositorios reais contra Postgres efemero (schema da SPEC-000), com rollback por teste.

## 7. Riscos

- Divergencia ORM vs schema do dicionario: coberta por testes de integracao.
- Geracao de protocolo unica: idempotencia por `idempotency_key` + unicidade no banco.

## 8. PR relacionado

- Branch: `feature/SPEC-001-legacy-rest-api`.
- PR #2 (em aberto): https://github.com/edgardamasceno-dev/khal-ai-challenge/pull/2
  - Implementacao via TDD (13 commits): VOs, entidades/use cases, infraestrutura
    (ORM+repos), borda REST e empacotamento (backend+gateway no compose).
  - Suite: 67 passed (unit+api+integration); ruff e mypy estrito limpos; 32
    asserts e2e no compose real.
