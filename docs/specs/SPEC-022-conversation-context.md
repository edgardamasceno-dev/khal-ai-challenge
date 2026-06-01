# SPEC-022 - `get_account_events` (ex `get_conversation_context`): tool de EVENTOS DE SISTEMA da conta + memoria por `titular_id` (R-03 + R-12)

- Status: Approved (2026-05-31)
- Versao alvo: 1.5.0 (os eventos proativos passam a ser legiveis pelo agente via tool MCP)
- ADRs: **ADR-0005 (revisao no mesmo PR)** — a injecao de memoria prometida deixa de
  ser "no backend que injeta o turno" e passa a ser cumprida por uma **tool MCP read-only**.
  **ADR-0013** — formaliza a fronteira de memoria do agente (transcricao Omni vs eventos
  desta store vs sessao Genie) e **renomeia** `get_conversation_context` → `get_account_events`.
  ADR-0012 (auditoria por tool-call) cobre a tool sem mudanca de mecanismo.
- Itens do roadmap: **R-03** (tool de eventos legivel) **+ R-12** (chave por `titular_id`,
  acoplado na mesma SPEC para a tool ja consumir a chave correta).
- Tool de transcricao conversacional (`get_chat_history`): **fora desta SPEC**, ver
  **SPEC-024** (fonte e uso distintos — Omni/WhatsApp vs `conversation_memory`).

## 1. Problema

O ADR-0005 prometia que os **eventos de sistema** gravados em `conversation_memory`
(pagamento confirmado, interrupcao aberta/encerrada, ultimo protocolo) chegariam ao
agente "pela entrada confiavel do canal", lidos no backend e **injetados** no turno. Essa
injecao **nunca foi implementada**: o spawn do agente so passa o `AGENTS.md` estatico.
Resultado: a **escrita** desses eventos e deterministica e correta
(worker/`ProactiveService`), mas o agente **nao le** nada — nao havia tool MCP de leitura.
O loop proativo↔reativo fica aberto: o cliente recebe "sua fatura foi paga" pelo fluxo
proativo e, no turno seguinte, o agente reoferece a 2a via da mesma fatura.

Havia ainda um segundo problema, de **nome**: a tool que materializou R-03 chamava-se
`get_conversation_context`, mas **nao** retorna a conversa — retorna **eventos tipados de
sistema**. O nome induzia o agente (e o leitor) a tratar fatos deterministicos como
transcricao, ou a nunca buscar o texto real da conversa (que vive no Omni). O ADR-0013
formaliza a fronteira e **renomeia** a tool para `get_account_events`.

Por fim, a memoria e chaveada por `chat_id == telefone E.164` (`EventoCX.chat_id` retorna
`self.telefone`; `ProactiveService.processar` grava com `chat_id=evento.chat_id`). Isso
fragmenta o contexto quando o titular tem **multiplas UCs** (SPEC-013) ou liga de **numero
diferente / LID** (SPEC-015). A chave correta e `titular_id` (R-12).

## 2. Objetivo

1. **R-03:** uma 10a tool MCP **read-only** `get_account_events(phone)` que resolve o
   titular pelo telefone do remetente e devolve os **eventos canonicos recentes de sistema**
   ja gravados, sob o **mesmo guardrail de acesso por telefone** das demais tools. O agente a
   chama no **abrir** da conversa (junto de `find_customer_by_phone`) para nao reoferecer o
   que o sistema ja resolveu (ex.: nao oferecer 2a via de fatura paga, nao reabrir chamado
   encerrado). **Nao** e a transcricao da conversa.
2. **R-12 (acoplado):** especificar a migracao da chave de memoria para `titular_id`, de modo
   que a tool ja consuma a chave correta, **sem quebrar** o `/{chat_id}/memory` legado (o
   console do operador le por chat).

> **Renomeacao (ADR-0013):** a tool e a **mesma** de hoje — read-only, lendo
> `conversation_memory`, mesmo guardrail, **assinatura/retorno externos inalterados**. Muda
> **apenas o nome** (`get_conversation_context` → `get_account_events`) e a **narrativa**
> (eventos de sistema, nao "conversation context"). A tool de transcricao
> (`get_chat_history`, SPEC-024) cobre o uso conversacional distinto.

## 3. Contrato da tool

```python
get_account_events(phone: str) -> dict[str, Any]
```

- **Sucesso (titular resolvido):**
  ```json
  {
    "encontrado": true,
    "titular": "Ana Souza",
    "itens": [
      {"chave": "proativo.pagamento.confirmado", "valor": {…}, "atualizado_em": "2026-05-30T12:00:00Z"}
    ],
    "total": 1
  }
  ```
  Itens **ordenados do mais recente para o mais antigo** e **truncados nas ultimas N=10**.
  `N` e default da tool (`_MEMORIA_LIMITE`, teto da tool), **nao** input do agente. Cada item
  corresponde a uma linha de `conversation_memory` gravada deterministicamente pelo
  `ProactiveService`/worker (ex.: `proativo.pagamento.confirmado`, `proativo.outage.encerrada`).
  Sao **eventos tipados de sistema**, nao texto de conversa.
- **Telefone nao resolve titular:** `{"encontrado": false, "motivo": "Telefone nao identificado."}`
  (mesmo formato das demais tools) — e a memoria **nao** e consultada.
- **Erro/vazio (best-effort):** `itens=[]`, sem quebrar nem afirmar ausencia.
- **Read-only:** nao escreve, nao muta estado.

## 4. Guardrail (deterministico, no codigo — nao no prompt)

1. Resolve o titular **sempre** pelo `phone` do remetente (contexto confiavel injetado pelo
   canal/Omni), **nunca** por id/telefone citado pelo cliente (nao contornavel por injection).
2. Se nao resolve titular → `{"encontrado": false}` e **nao** consulta memoria.
3. Le **apenas** a memoria do proprio titular pelas **variantes canonicas do telefone
   normalizado** (`variantes_nono_digito` sobre `normalizar_msisdn`, SPEC-015), **nunca** o
   telefone cru recebido. Para na primeira variante com memoria.
4. Auditada por `AuditedCxTools` como as demais (ADR-0012): log estruturado + sink best-effort,
   PII mascarada (`phone` → sufixo de 4 digitos).

## 5. Escopo

### MCP (R-03 — entregue nesta SPEC)
- `ports.py`: `LegacyApiClient` += `get_conversation_memory(chat: str, limit: int = 10) -> list[dict]`.
- `client.py`: `HttpxLegacyApiClient.get_conversation_memory` → `GET /conversations/{chat}/memory`
  (envia `?limit=` por cortesia; a truncagem definitiva e no CxTools, o router legado pode
  ignorar o parametro sem quebrar).
- `tools.py`: `CxTools.get_account_events(phone)` + helper privado
  `_ler_memoria_do_titular(phone)` (resolve variantes canonicas, ordena, trunca em N=10).
- `audit.py`: `AuditedCxTools.get_account_events` (espelha a superficie, instrumentada).
- `server.py`: 10a `@mcp.tool() get_account_events` (registrada **por ultimo entre as 10**, na
  posicao 10 da ordem canonica → ordem estavel para a allowlist do R-02 / cache R-07; a 11a,
  `get_chat_history`, e registrada depois — SPEC-024).
- Allowlist (R-02, fonte unica `src/interfaces/mcp/allowlist.py`): a tool entra como **10o**
  nome (`get_account_events`), habilitada em **producao** (frontmatter) e nos **evals**
  (`run.py`), com **teste de paridade** que impede drift.
- `AGENTS.md`: secao "Memoria e historico (duas fontes distintas — nunca confunda)" descreve
  `get_account_events` (fatos de sistema) vs `get_chat_history` (transcricao, SPEC-024); regra
  pratica "o que o SISTEMA fez → `get_account_events`; o que foi DITO → `get_chat_history`".

> **Renomeacao no stack inteiro:** `server.py` (`@mcp.tool`), `CxTools` + `AuditedCxTools`,
> `allowlist.TOOL_NAMES[9]`, frontmatter, eval-scope e `AGENTS.md` passam de
> `get_conversation_context` para `get_account_events`. Nada do **comportamento** muda.

### REST (reuso, R-03 puro)
- **Sem endpoint novo** para R-03: reusa `GET /conversations/{chat_id}/memory`
  (`src/interfaces/rest/routers/conversation.py:14`, `response_model=list[MemoryItemDTO]`
  → `[{chave, valor, atualizado_em}]`). O `chat_id` e o telefone.
- Desejavel (barato, opcional): aceitar `?limit=` no router e em `MemoryService.get` para
  truncar no servidor. Enquanto nao houver, a truncagem ocorre no CxTools.

### R-12 (acoplado — chave por `titular_id`)
- Migracao Alembic: `conversation_memory` reindexada por `titular_id` (resolvido via
  `BillingService.find_customer_by_phone`), mantendo `chat_id` como **chave secundaria** para
  registros sem `titular_id` resolvivel (fallback idempotente).
- `MemoriaRepository.list_for_titular(titular_id)` + `MemoryService.get_por_titular`.
- **Endpoint novo:** `GET /conversations/by-titular/{titular_id}/memory` (mesmo
  `response_model`), **sem quebrar** `/{chat_id}/memory` (console por chat).
- A tool migra **por dentro**: `_ler_memoria_do_titular` passa a chamar
  `get_conversation_memory_by_titular(titular_id)` — **a assinatura e o retorno externos da
  tool nao mudam** (`get_account_events(phone) -> mesmo dict`). So muda o adapter REST.
- **R-12 (chave por `titular_id`)** permanece intacto nesta SPEC: a renomeacao da tool nao
  altera a regra de chaveamento da memoria nem o fallback.

## 6. Fora de escopo

- **Transcricao conversacional** (texto cru do que foi DITO): e a tool `get_chat_history` da
  **SPEC-024** (fonte Omni/WhatsApp, uso distinto — recuperacao de fio pos cold-start).
- Memoria semantica de longo prazo / recall por similaridade (R-15).
- Resumo/compactacao da memoria por LLM (R-08/R-15).
- Escrita de memoria pela tool (a tool e read-only; a escrita continua 100% deterministica no
  worker/`ProactiveService`).

## 7. Plano TDD

1. **Port/adapter** (unit): `get_conversation_memory` faz `GET` com `?limit=` e devolve a lista.
2. **Tool** (unit, fakes):
   - retorna os eventos do titular (chaves canonicas presentes);
   - itens do mais recente para o mais antigo;
   - telefone desconhecido → `encontrado=false` e **nao** consulta memoria;
   - **nao vaza** memoria de outro titular (Carlos nao recebe a memoria da Ana);
   - best-effort sem memoria (itens vazios, sem quebrar).
3. **Paridade (R-02)** `tests/unit/test_mcp_allowlist_parity.py` / `test_tool_scope_parity.py`:
   `get_account_events` presente nas 3 fontes (server, eval-scope, frontmatter) na posicao 10;
   server == allowlist em conjunto e ordem.
4. **Contagem:** `server.py` registra `get_account_events` como 10a tool (a 11a,
   `get_chat_history`, vem da SPEC-024).
5. **R-12:** migracao idempotente + endpoint `by-titular` + repo `list_for_titular`, com
   fallback para `chat_id`; suite de regressao verde (console por chat segue funcionando).

## 8. Criterios de aceite

- No 1o turno, o agente chama `find_customer_by_phone` **e** `get_account_events` e
  **nao** reoferece a 2a via de uma fatura ja marcada como paga na memoria.
- Guardrail: telefone sem titular → `encontrado=false`, **sem** leitura de memoria; a tool
  jamais devolve memoria de chat que nao seja do titular resolvido.
- A tool aparece em **producao** (frontmatter) **e** nos **evals** com o nome
  `get_account_events`, e o teste de paridade bloqueia drift (cobre R-02 + R-03).
- R-12: memoria chaveada por `titular_id` com fallback `chat_id`; assinatura/retorno externos
  da tool inalterados.
- unit + api + integration + lint/typecheck verdes.

## 9. Notas

- A tool **nao** precisa de endpoint novo para R-03 puro porque `chat_id == telefone`. O
  endpoint `by-titular` so entra com R-12 e e aditivo.
- Ordem de registro em `server.py` = ordem em `allowlist.TOOL_NAMES` = ordem em `run.py`:
  pre-requisito de prompt caching (R-07) e contrato do teste de paridade.
- **Fronteira de memoria (ADR-0013):** `get_account_events` cobre os **eventos de sistema**
  (esta store); `get_chat_history` (SPEC-024) cobre a **transcricao** (Omni); a **sessao**
  (Genie) e fonte volatil sem tool propria. As duas tools sao read-only e resolvem o titular
  pelo telefone do remetente.
