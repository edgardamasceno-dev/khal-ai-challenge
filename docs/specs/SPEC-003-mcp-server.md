# SPEC-003 - MCP server (ferramentas do agente)

- Status: Draft
- Versao alvo: 0.4.0 (camada de ferramentas exposta ao agente)
- ADRs: ADR-0001 (Python/Pydantic), ADR-0006 (compose, increment 4 - mcp-server). MCP-over-REST (doc 09).
- Validado antes em POC (`poc/mcp-server`, 14/14 via cliente MCP, direto e pelo gateway).

## 1. Problema

O agente (Genie/Claude Code) precisa de ferramentas tipadas para agir sobre o
negocio. A API legada (SPEC-001) existe, mas o agente nao fala REST: ele fala MCP.
Sem um MCP server, nao ha como o agente consultar/agir com guardrails.

## 2. Objetivo

Promover o MCP server validado no POC para `implementation/src/interfaces/mcp`:
servidor FastMCP (HTTP streamable) que expoe as ferramentas chamando a API legada
por dentro da rede (**MCP-over-REST**), com guardrails **determinISticos** no codigo.
Implementacao via **TDD**: a logica das tools e testada contra um client legado fake.

## 3. Escopo

Ferramentas: `find_customer_by_phone`, `list_contracts`, `get_invoice_status`,
`get_outage_by_region`, `create_ticket`, `get_ticket_status`, `request_human_handoff`.

Arquitetura (hexagonal): `LegacyApiClient` (port) + adapter httpx; `CxTools`
(use cases das tools com guardrails) testavel contra um fake; `server.py` (wiring
FastMCP). Servico `mcp-server` no compose + rota `/mcp` no gateway.

Guardrails determinISticos:
- Acesso pelo telefone do remetente; titular resolvido no servidor; ids de
  cliente/UC nunca vem do agente (nao contornavel por injection).
- Confirmacao obrigatoria antes de escrever (`create_ticket`).
- Idempotencia por chave deterministica (telefone, tipo, descricao).
- `get_ticket_status` so devolve chamado do titular do telefone.

## 4. Fora de escopo

- Agente em si (`AGENTS.md`/policy - SPEC seguinte) e wiring Omni/Genie no sandbox.
- `search_knowledge_base` (depende da KB, ADR-0004 / SPEC de Knowledge).
- Memoria/eventos (ADR-0005).

## 5. Criterios de aceite

- As 7 tools aparecem no `tools/list` e respondem via MCP (validacao e2e no compose).
- Guardrails ativos: telefone desconhecido nao vaza dados; `create_ticket` exige
  confirmacao; mesma chave nao duplica; protocolo de outro cliente e negado.
- Suite verde (unit das tools + suites anteriores); ruff e mypy estrito limpos.

## 6. Plano de testes (TDD - cenarios)

Unit das tools contra `FakeLegacyApiClient` (sem rede), cobrindo inclusive as bordas
levantadas na revisao do POC:

- `find_customer_by_phone`: conhecido; desconhecido.
- `list_contracts`: conhecido; **telefone desconhecido**.
- `get_invoice_status`: com faturas em aberto; **sem faturas em aberto**; **telefone desconhecido**.
- `get_outage_by_region`: interrupcao ativa; ausente.
- `create_ticket`: `confirmar=false` -> needs_confirmation; confirmado -> protocolo;
  **idempotente** (mesma chave); **tipo invalido (422)**; **telefone desconhecido**.
- `get_ticket_status`: do titular; **protocolo inexistente (404)**; **protocolo de outro cliente (guardrail)**.
- `request_human_handoff`: ok; **telefone desconhecido**.

E2E (sem TDD): cliente MCP contra o `mcp-server` no compose (direto e via gateway `/mcp`).

## 7. Riscos

- Drift entre as tools e os DTOs do backend: mitigado pelo port + testes; e2e confirma o contrato real.
- Transporte streamable-HTTP atras do nginx: `proxy_buffering off`, HTTP/1.1, timeout alto.

## 8. PR relacionado

- Branch: `feature/SPEC-003-mcp-server`. PR a preencher ao abrir.
