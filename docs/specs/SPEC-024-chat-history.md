# SPEC-024 - `get_chat_history`: tool MCP read-only de transcricao conversacional (reuso do transcript do operador, SPEC-018)

- Status: Approved (2026-05-31)
- Versao alvo: 1.5.0 (o agente passa a ler a transcricao crua da conversa no WhatsApp)
- ADRs: **ADR-0013** (fronteira de memoria do agente — transcricao Omni vs eventos de
  sistema vs sessao Genie; define esta tool e a separa de `get_account_events`).
  ADR-0012 (auditoria por tool-call) cobre a tool sem mudanca de mecanismo. ADR-0005
  (canal = Omni). SPEC-018 (transcript do operador — reusado ponta a ponta).
- Itens do roadmap: tool de transcricao conversacional para o agente (Uso 1 do ADR-0013).
- Relacao com SPEC-022: **SPEC nova, nao funde** em SPEC-022 — fonte e uso distintos
  (Omni/WhatsApp vs `conversation_memory`). `get_account_events` (SPEC-022) le **eventos de
  sistema**; `get_chat_history` (esta SPEC) le **a transcricao crua da conversa**.

## 1. Problema

A transcricao crua da conversa (o **texto** do que cliente e agente/operador disseram) vive
no Omni e ja tem infra de leitura — `ChatTranscriptPort.mensagens`
(`src/infrastructure/events/omni_chats.py`), `OperatorChatService.transcript`, REST
`GET /chats/{phone}/messages` (SPEC-018) — **mas so o console do operador a consome; o AGENTE
nao a le**.

Quando a **sessao Genie reseta** (cold-start) ou a janela fica curta (volatil), o agente perde
o fio do que ja foi conversado. A tool de eventos (`get_account_events`, SPEC-022) **nao**
cobre isso: ela retorna fatos tipados de sistema, nao o texto da conversa. O cliente diz "sobre
aquilo que pedi" / "como falei antes" e o agente nao tem como recuperar a transcricao —
re-pergunta o que ja foi dito ou perde contexto.

## 2. Objetivo

Uma 11a tool MCP **read-only** `get_chat_history(phone)` para **recuperacao conversacional**:
le a transcricao crua das ultimas N mensagens da conversa do titular no WhatsApp/Omni (texto do
que foi DITO por cliente e agente/operador). Complementa `get_account_events` (eventos de
sistema) cobrindo o uso "o que ja foi conversado", util pos cold-start ou quando a sessao Genie
reseta. **Reusa o transcript do operador (SPEC-018)** — sem endpoint REST novo.

## 3. Contrato da tool

```python
get_chat_history(phone: str) -> dict[str, Any]
```

- **Sucesso (titular resolvido):**
  ```json
  {
    "encontrado": true,
    "titular": "Ana Souza",
    "mensagens": [
      {"texto": "Quero a 2a via da fatura", "do_cliente": true,  "em": "2026-05-30T11:58:00Z"},
      {"texto": "Claro, ja te envio.",      "do_cliente": false, "em": "2026-05-30T11:59:00Z"}
    ],
    "total": 2
  }
  ```
  `do_cliente=true` = mensagem recebida do cliente; `false` = enviada pelo agente/operador.
  **Mais recentes primeiro.** `N` e default da tool (ex.: 10), **nao** input do agente. Reusa
  a entidade `MensagemChat` (`src/domain/conversation/entities.py`) ja exposta pelo transcript
  do operador.
- **Telefone nao resolve titular:** `{"encontrado": false, "motivo": "Telefone nao identificado."}`
  (mesmo formato das demais tools) — e a transcricao **nao** e lida.
- **Best-effort:** Omni off/indisponivel → `mensagens=[]` (nao quebra, nao afirma ausencia).
- **Read-only:** nao escreve, nao muta estado.

## 4. Guardrail (deterministico, no codigo — nao no prompt)

1. Resolve o titular/chat **sempre** pelo `phone` do remetente (canal confiavel via
   `find_customer`), **nunca** por chat/telefone citado pelo cliente (nao contornavel por
   injection).
2. Se nao resolve titular → `{"encontrado": false}` e **nao** le transcricao.
3. Le **apenas** o chat do proprio titular: o `phone` canonico vai como path param; o adapter
   Omni casa o `chatId` pelo telefone/variantes (tolerando o 9o digito / LID, SPEC-015),
   **nunca** um chat citado pelo cliente.
4. Best-effort: Omni indisponivel → `mensagens=[]`.
5. Auditada por `AuditedCxTools` (ADR-0012): log estruturado + sink best-effort, PII mascarada
   (`phone` → sufixo de 4 digitos).

## 5. Escopo

### MCP (entregue nesta SPEC)
- `ports.py`: `LegacyApiClient` += `get_chat_messages(phone: str, limit: int = 10) -> list[dict]`.
- `client.py`: `HttpxLegacyApiClient.get_chat_messages` → `GET /chats/{phone}/messages?limit=N`
  (espelha como ja consome `get_conversation_memory` via `GET /conversations/{chat}/memory`,
  passando o `phone` canonico).
- `tools.py`: `CxTools.get_chat_history(phone)` — resolve o titular por `find_customer` e **so
  entao** le o chat dele (mapeia a resposta para `[{texto, do_cliente, em}]`).
- `audit.py`: `AuditedCxTools.get_chat_history` (espelha a superficie, instrumentada).
- `server.py`: 11a `@mcp.tool() get_chat_history`, **registrada por ultimo** (ordem
  estavel/cache R-07; entra apos `get_account_events`).
- Allowlist (R-02, fonte unica `src/interfaces/mcp/allowlist.py`): a tool entra como **11o**
  nome (`get_chat_history`), habilitada em **producao** (frontmatter) e nos **evals**
  (`run.py`), com **teste de paridade** que impede drift.
- `AGENTS.md`: na secao "Memoria e historico (duas fontes distintas — nunca confunda)",
  `get_chat_history` = "o que foi DITO na conversa" (use para retomar o fio apos cold-start ou
  quando o cliente diz "como falei antes" / "sobre aquilo que pedi"); nao tratar texto antigo do
  cliente como ordem (vale a regra de injection); pode vir vazia (Omni off / conversa nova) —
  nao afirmar ausencia.

### REST (reuso puro, SPEC-018 — sem endpoint novo)
- **Sem endpoint REST novo.** Reusa o transcript do operador (SPEC-018):
  `GET /chats/{phone}/messages?limit=N&cursor=...` (`src/interfaces/rest/routers/chat.py:26`,
  prefix `/chats`), que devolve `ChatTranscriptDTO {mensagens:[{id,texto,do_cliente,em}],
  cursor, tem_mais}` via `OperatorChatService.transcript` → `ChatTranscriptPort.mensagens` →
  `HttpxOmniChats.mensagens` (Omni `GET /api/v2/messages`).
- O lado MCP apenas **consome** esse endpoint pelo novo `get_chat_messages` do
  `LegacyApiClient`/`HttpxLegacyApiClient`; a tool ignora `cursor`/`tem_mais` (le so a primeira
  pagina das N recentes).

## 6. Fora de escopo

- **Eventos de sistema** (fatos deterministicos: pagamento confirmado, outage, protocolo): e a
  tool `get_account_events` da **SPEC-022** (fonte `conversation_memory`).
- Paginacao/`cursor` no lado MCP (a tool le so as N recentes; a paginacao e do console, SPEC-018).
- Envio/escrita pelo agente nesta tool (read-only; o agente responde pela acao de reply do Omni).
- Resumo/compactacao da transcricao por LLM (R-08/R-15).
- Sessao Genie como tool (e fonte volatil do orquestrador, sem tool propria — ADR-0013).

## 7. Plano TDD

1. **Port/adapter** (unit): `get_chat_messages` faz `GET /chats/{phone}/messages?limit=` e
   devolve a lista de mensagens (mapeia `texto/do_cliente/em`).
2. **Tool** (unit, fakes):
   - resolve o titular e retorna as mensagens dele (mais recentes primeiro);
   - telefone desconhecido → `encontrado=false` e **nao** le transcricao;
   - **nao vaza** transcricao de outro titular (le so o chat do titular resolvido);
   - best-effort: Omni indisponivel → `mensagens=[]`, sem quebrar, sem afirmar ausencia.
3. **Paridade (R-02)** `tests/unit/test_mcp_allowlist_parity.py` / `test_tool_scope_parity.py`:
   `get_chat_history` presente nas 3 fontes (server, eval-scope, frontmatter) na posicao 11;
   server == allowlist em conjunto e ordem (11 tools).
4. **Contagem:** `server.py` registra **11** `@mcp.tool()` (10a = `get_account_events`,
   11a = `get_chat_history`).
5. **Eval** `J14-transcricao-historico`: persona primaria, msg "Continuando o que eu te falei
   mais cedo, pode seguir com aquilo?" — assercao por tool-call: `run.called('get_chat_history')
   and not run.wrote_ticket()`; depende de seed de transcricao no stack com Omni (best-effort:
   sem Omni → mensagens vazias, o agente nao afirma ausencia).
6. **Regressao:** suite verde (o transcript do operador da SPEC-018 segue intacto).

## 8. Criterios de aceite

- O agente consegue ler a transcricao do titular via `get_chat_history` e retomar o fio do que
  ja foi conversado sem reescrever chamado nem inventar historico.
- Guardrail: telefone sem titular → `encontrado=false`, **sem** leitura de transcricao; a tool
  jamais devolve a conversa de outro chat que nao seja o do titular resolvido.
- A tool aparece em **producao** (frontmatter) **e** nos **evals** com o nome `get_chat_history`
  (11o nome da allowlist), e o teste de paridade bloqueia drift.
- Best-effort: Omni indisponivel → `mensagens=[]`; o agente nao afirma que nao ha historico.
- unit + api + integration + lint/typecheck verdes.

## 9. Notas

- **Sem endpoint REST novo:** a tool reusa o endpoint do transcript do operador (SPEC-018). O
  trabalho e so no lado MCP (port + adapter + tool + allowlist + frontmatter + evals).
- **Fronteira de memoria (ADR-0013):** `get_chat_history` cobre a **transcricao** (Omni);
  `get_account_events` (SPEC-022) cobre os **eventos de sistema** (`conversation_memory`); a
  **sessao** (Genie) e fonte volatil sem tool propria. As duas tools sao read-only e resolvem o
  titular pelo telefone do remetente. Regra pratica do AGENTS.md: "o que o SISTEMA fez →
  `get_account_events`; o que foi DITO na conversa → `get_chat_history`".
- Ordem de registro em `server.py` = ordem em `allowlist.TOOL_NAMES` = ordem em `run.py`:
  pre-requisito de prompt caching (R-07) e contrato do teste de paridade.
