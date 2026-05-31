# SPEC-020 - Encerrar chamado pelo operador (+ aviso por WhatsApp no ciclo de vida)

- Status: Approved (2026-05-31)
- Versao alvo: 1.6.0 (operador encerra o chamado; titular é avisado no WhatsApp)
- ADRs: ADR-0002 (console fino), ADR-0003 (saída de mídia/canal pelo Omni), ADR-0005
  (notificações determinísticas, sem LLM). Sem ADR novo.

## 1. Problema

O chamado nasce `aberto` (SPEC-001/003) e **nunca muda de estado**: não há como o
operador **encerrá-lo** pelo console, nem o cliente é avisado quando o chamado é
**aberto** ou **resolvido**. O ciclo de vida do chamado fica preso e silencioso — o
titular acompanha pela conversa, mas não recebe nada determinístico no WhatsApp ao
abrir/encerrar.

## 2. Objetivo

Permitir que o operador **encerre o chamado como `resolvido`** direto na aba Chamados e,
ao abrir/encerrar pelo console, **avisar o titular por WhatsApp** com uma mensagem
**determinística** (sem LLM). O agente MCP **não** notifica ao abrir (ele já responde o
cliente na própria conversa); só o **console** dispara o aviso.

### Decisões

- **Estado do chamado** vira um value object explícito `StatusChamado` (`aberto` ->
  `resolvido`). Por enquanto só esses dois estados (encerrar é a única transição do
  operador).
- O encerramento é **idempotente**: reencerrar um chamado já `resolvido` não muta nada e
  **não reenvia** a notificação; protocolo inexistente -> **404** (`NotFoundError`).
- A notificação é **determinística** e **best-effort** (ADR-0005): templates puros em
  `ticketing/mensagens.py`, envio pelo canal Omni (ADR-0003) via `OmniSender.send_text`.
  Se não houver `sender`/`OMNI_INSTANCE_ID`, o envio é **no-op** e o encerramento segue
  registrado — a notificação nunca derruba a operação.
- **Quem notifica ao abrir**: `open_ticket(notificar=False)` por **default**, então o
  agente MCP (`create_ticket`) **não** avisa (já responde na conversa). O **console**
  envia `notificar=true` ao abrir, para o titular receber o aviso por WhatsApp.

## 3. Escopo

### Domínio
- `StatusChamado` (StrEnum) em `src/domain/shared/value_objects.py`: `aberto` |
  `resolvido` (o operador encerra `aberto` -> `resolvido`).
- `src/domain/ticketing/mensagens.py` (funções **puras**, sem LLM):
  `mensagem_chamado_aberto(nome, chamado)` e `mensagem_chamado_resolvido(nome, chamado)`
  — usam o primeiro nome do titular, o protocolo, o rótulo do tipo e o SLA.

### Back
- `ChamadoRepository.set_status(protocolo, status, atualizado_em) -> Chamado | None`
  (port) + `SqlChamadoRepository.set_status` (seta `status`/`atualizado_em` por
  protocolo; `None` se não existir).
- `TicketingService`:
  - ganha `sender: OmniSender | None` (injetado) e o helper `_notificar(titular, texto)`
    — **best-effort**: sem sender é no-op, e o `OmniSender` retorna bool (não lança).
  - `open_ticket(..., notificar=False)`: ao criar (não no caminho idempotente), se
    `notificar` é `True`, dispara `mensagem_chamado_aberto`.
  - `resolve_ticket(protocolo) -> Chamado`: idempotente (já `resolvido` -> retorna sem
    reenviar) + `NotFoundError` (404) se o protocolo não existe; muta via `set_status`,
    `commit` e notifica `mensagem_chamado_resolvido`.
- REST: `POST /tickets/{protocolo}/resolve` -> `resolve_ticket` -> `TicketDTO`.
  `CreateTicketRequest` ganha `notificar: bool = False` (repassado a `open_ticket`).
- DI: `get_ticketing_service` injeta `HttpxOmniSender` (`omni_url`/`omni_api_key`/
  `omni_instance_id`). `docker-compose.yml` expõe `OMNI_INSTANCE_ID` ao backend.

### Front (console)
- `TicketsSection`: nova coluna de ações com um **dropdown** por linha (apenas para
  chamados `aberto`) com a opção **"Encerrar como resolvido"** -> `api.resolveTicket` ->
  recarrega; toast informa que o cliente foi avisado no WhatsApp.
- `CreateTicketDialog` passa `notificar: true` ao abrir; o toast de criação avisa que o
  cliente foi notificado.
- `ui/src/lib/api.ts`: `resolveTicket(protocolo)` (`POST /tickets/{protocolo}/resolve`) e
  `notificar?` opcional em `createTicket`. Componente `dropdown-menu` (shadcn).

## 4. Fora de escopo

- Outros estados além de `aberto`/`resolvido` (ex.: `cancelado`, `em_andamento`) e
  histórico de transições (só o estado corrente + `atualizado_em`).
- Reabrir um chamado resolvido pelo console.
- Encerramento pelo **agente MCP**: a transição é ação do operador (ADR-0002); o agente
  só abre/consulta.
- LLM em qualquer ponto da notificação (ADR-0005); garantia de entrega no WhatsApp (é
  best-effort pelo Omni — ADR-0003).

## 5. Plano TDD

> Cobertura entregue (back). Os testes cobrem a fatia de back/domínio; a fatia de
> front (item 5) continua validada pelo build do console.

1. **Domínio** (unit): `StatusChamado` (`aberto`/`resolvido`) em
   `tests/unit/test_value_objects.py::TestStatusChamado`; `mensagem_chamado_aberto`
   e `mensagem_chamado_resolvido` rendem protocolo/primeiro nome/tipo/SLA de forma
   determinística em `tests/unit/test_ticketing_mensagens.py` (prova nome composto ->
   primeiro nome).
2. **Repo** (integration): `tests/integration/test_repositories.py::TestTicketingRepos`
   — `set_status` persiste `status`/`atualizado_em` por protocolo (leitura reflete o
   novo estado); protocolo inexistente -> `None`.
3. **Service** (unit, fakes): `tests/unit/test_services.py::TestTicketingService` —
   `resolve_ticket` muta + commita + notifica (chama o `OmniSender` uma vez);
   reencerrar `resolvido` é no-op (sem remutar/reenviar); protocolo inexistente ->
   `NotFoundError` sem commit; sender ausente -> sem envio (no-op), encerramento segue;
   `open_ticket(notificar=True)` notifica ao criar, `notificar=False` (default) não
   notifica e o caminho idempotente nunca notifica.
4. **REST** (api): `tests/api/test_api.py::TestTicketingApi` —
   `POST /tickets/{protocolo}/resolve` -> 200 + `TicketDTO` `resolvido` (idempotente,
   sem reenvio); inexistente -> 404; `create_ticket` repassa `notificar` (default não
   avisa; `notificar=true` avisa o titular).
5. **Front**: dropdown "Encerrar como resolvido" só em `aberto` -> chama `resolveTicket` +
   recarrega; criar passa `notificar:true` (build do console).
6. **Regressão**: suite verde; evals não afetados (agente não notifica/encerra).

## 6. Critérios de aceite

- Operador encerra pelo console -> chamado vira `resolvido` no banco e o titular recebe a
  mensagem determinística no WhatsApp (best-effort).
- Reencerrar um chamado já `resolvido` não reenvia a notificação; protocolo inexistente
  retorna 404.
- Abrir pelo console (`notificar=true`) avisa o titular; abrir pelo agente MCP
  (`notificar=false`) **não** avisa (o agente já respondeu na conversa).
- Sem `OMNI_INSTANCE_ID`/sender, a notificação é no-op e a operação não quebra.
- unit+integration+api+lint/typecheck verdes; console builda.
