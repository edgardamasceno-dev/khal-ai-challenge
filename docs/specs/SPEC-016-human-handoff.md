# SPEC-016 - Handoff humano determinístico (pausa a IA no Omni)

- Status: Approved (2026-05-30)
- Versao alvo: 1.4.0 (handoff pausa o agente; retomada pelo console)
- ADRs: ADR-0005 (determinístico, sem LLM). Sem ADR novo.

## 1. Problema

Pedir "falar com atendente" não muda nada: a IA continua respondendo. O esperado é
**pausar a IA** naquele chat e operar **humano ↔ humano**, com o histórico salvo, e o
operador **retomar** quando quiser.

## 2. Viabilidade (Omni)

O Omni suporta nativamente: `chat.settings.agentPaused = true` faz o agent-dispatcher
**pular o agente** (`agent-dispatcher.ts`). Set via `PATCH /api/v2/chats/:id`
(`{settings:{agentPaused:true}}`), genérico (Baileys). A persistência de mensagens é
**desacoplada** do agente — inbound e mensagens do humano são salvas mesmo com a IA
pausada. Retomar: `agentPaused:false`.

## 3. Escopo

### Schema
- `handoff_queue` += `remetente text` (id do chat: LID/telefone) para pausar/retomar.

### Back
- `ChannelControlPort` + adapter (Omni): `pausar_agente(remetente)` / `retomar_agente(remetente)`
  resolvem o **chat id** (`/api/v2/chats` por `externalId`/`canonicalId`) e fazem o PATCH.
  Best-effort (Omni off -> retorna False; handoff segue registrado).
- `HandoffRepository`: `add` (com `remetente`), `list_pendentes()`, `get(id)`,
  `set_status(id, status, operador)`.
- `TicketingService`: `request_handoff(remetente, chamado_id, motivo)` cria o handoff e
  **pausa** a IA; `list_handoffs()`; `resume_handoff(id, operador)` **retoma** + marca `resolvido`.
- REST: `POST /handoffs` (recebe `remetente`, pausa), `GET /handoffs` (fila de pendentes),
  `POST /handoffs/{id}/resume` (retoma).

### MCP
- `request_human_handoff(phone, motivo)` envia `remetente=phone` ao backend (que pausa).

### Front (console)
- Aba **Chamados**: card "Atendimento humano" lista os handoffs **pendentes** (nome/motivo,
  quando) com botão **Devolver à IA** -> `POST /handoffs/{id}/resume`, recarrega.

## 4. Fora de escopo

- Interface de chat humano-humano (o humano responde pelo próprio WhatsApp/Omni).
- Roteamento por operador / SLA de fila (só pendente -> resolvido).

## 5. Plano TDD

1. **Repo** (integration): `add` com remetente; `list_pendentes`; `set_status`.
2. **Adapter** (unit, mock): resolve o chat id e faz PATCH; Omni off -> False.
3. **Service** (unit, fakes): `request_handoff` cria + pausa; `resume_handoff` retoma + resolve.
4. **REST** (api): `POST /handoffs` pausa; `GET /handoffs` lista; `resume` retoma.
5. **Front**: card de pendentes + botão (build do console).
6. **Regressão**: suite verde.

## 6. Critérios de aceite

- Pedir atendente -> handoff registrado + IA pausada no Omni (`agentPaused=true`).
- Operador retoma pelo console -> IA volta (`agentPaused=false`) + handoff `resolvido`.
- Histórico preservado (Omni). unit+integration+api+lint/typecheck verdes; console builda.
