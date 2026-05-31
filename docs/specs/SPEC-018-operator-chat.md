# SPEC-018 - Aba Chat do operador (transcript + takeover)

- Status: Approved (2026-05-31)
- Versao alvo: 1.5.0 (console mostra a conversa e permite o humano assumir)
- ADRs: ADR-0002 (console fino), ADR-0005 (canal = Omni). Sem ADR novo.

## 1. Problema

O operador não vê a conversa do cliente com o agente, nem consegue responder pelo
console. Hoje "assumir" só existe via fila de handoff (SPEC-016), sem ver as mensagens
nem digitar a resposta.

## 2. Objetivo

Uma aba **Chat** (entre Chamados e Proativos) que mostra a conversa do WhatsApp
(estilo app de mensagens), permite o operador **assumir o controle** (pausa a IA) e
**responder**, e **devolver ao agente**. Atualização automática preservando a paginação.

## 3. Decisões

- **Fonte = Omni** (histórico real do WhatsApp): `GET /api/v2/messages?chatId&limit&cursor`
  (cursor por timestamp; página seguinte = mais antigas; `meta.hasMore`). Campos:
  `textContent`, `isFromMe`, `platformTimestamp`.
- **Assumir/devolver = `agentPaused`** (reusa SPEC-016): assumir -> `pausar_agente`;
  devolver -> `retomar_agente`. Enquanto pausado, a IA não responde e o operador digita.
- **Identificador = telefone** do cliente (a UI já tem); o backend resolve o chat id.
- Backend faz **proxy** do Omni (a UI não fala com o Omni direto).

## 4. Escopo

### Back
- `ChatTranscriptPort` + `HttpxOmniChats`: `mensagens(remetente, limit, cursor)` ->
  `(itens, proximo_cursor, tem_mais)`; `esta_pausado(remetente)`.
- `OperatorChatService`: `transcript`, `status` (pausado?), `takeover` (pausa),
  `release` (retoma), `send` (operador envia via `OmniSender.send_text`).
- REST: `GET /chats/{phone}/messages?limit=10&cursor=`, `GET /chats/{phone}/status`,
  `POST /chats/{phone}/takeover`, `POST /chats/{phone}/release`,
  `POST /chats/{phone}/send {texto}`. DTO de msg: `{texto, do_cliente, em}`.

### Front (console)
- Aba **Chat** (entre Chamados e Proativos). Mensagens em ordem cronológica (antigas em
  cima, recentes embaixo; bolhas: cliente à esquerda, agente/operador à direita), scroll
  inicia no fim. **Mostrar mais** no topo carrega as 10 anteriores (preserva o scroll).
- Pílula de status (IA ativa / Você no controle). **Assumir controle** -> input + Enviar;
  **Devolver ao agente** -> esconde o input.
- **Auto-refresh** (poll ~5s): busca as 10 recentes e faz *merge* por id, mantendo as
  páginas já carregadas via "Mostrar mais"; atualiza o status.

## 5. Fora de escopo

- Anexos do operador (só texto); reações; busca na conversa.
- Notificação de nova mensagem fora da aba.

## 6. Plano TDD

1. **Adapter** (unit, mock): `mensagens` mapeia textContent/isFromMe/timestamp + cursor;
   `esta_pausado` lê settings.agentPaused.
2. **Service** (unit, fakes): transcript; takeover/release chamam pausar/retomar;
   send usa o OmniSender.
3. **REST** (api): GET messages/status; takeover/release; POST send.
4. **Front**: aba, paginação (mostrar mais), takeover (input), auto-refresh (build).
5. **Regressão**: suite verde.

## 7. Critérios de aceite

- Aba Chat mostra as 10 mais recentes; "Mostrar mais" pagina as anteriores.
- Assumir controle pausa a IA e habilita o envio; devolver retoma.
- Auto-refresh traz novas mensagens sem perder as páginas carregadas.
- unit+api+lint/typecheck verdes; console builda.
