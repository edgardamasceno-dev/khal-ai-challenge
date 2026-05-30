# ADR-0001 - Stack Python/Pydantic na camada de ferramentas

- Status: Accepted
- Data: 2026-05-30

## Context

O desafio exige um agente WhatsApp com Omni (canal) e Genie (orquestrador), ambos TypeScript/Bun. A camada de ferramentas (MCP server + API do "sistema legado") e desacoplada do Omni/Genie por contratos (MCP/REST), entao sua linguagem e uma escolha independente.

As vagas alvo (Lead e Senior FDE) citam **Pydantic AI** como diferencial/esperado e valorizam modelagem e validacao de estruturas de agente. A "nativez em Omni/Genie" vem do wiring correto (CLI, agent dir, subjects NATS, contrato de reply), nao da linguagem da ferramenta.

## Decision

Implementar a camada de ferramentas em **Python 3.12 com Pydantic v2** (FastAPI para a API legada, MCP Python SDK para o servidor de ferramentas). A UI fica em React/TypeScript. O agente no Genie e `AGENTS.md` + configuracao de MCP (markdown/config, agnostico de linguagem).

## Consequences

Positivas:
- Acerta um diferencial nomeado da vaga (Pydantic).
- Contratos tipados e validados em runtime servem como guardrail.
- FastAPI gera OpenAPI -> cliente tipado para a UI de graca.

Negativas:
- Nao reusa SDKs TS do Omni/Genie diretamente. Mitigacao: outbound usa a API REST publica do Omni (`httpx`), que e estavel.
- Introduz duas linguagens (Python + TS na UI). Mitigado por contrato OpenAPI entre elas.

## Alternatives

- **TypeScript/Bun como stack principal**: maximizaria "nativez" superficial, mas perde o diferencial Pydantic; rejeitado para a camada de ferramentas, mantido apenas na UI.
- **Agno para orquestracao**: quem orquestra e o Genie; seria redundante.
