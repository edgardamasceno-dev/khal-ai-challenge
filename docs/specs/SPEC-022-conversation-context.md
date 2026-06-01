# SPEC-022 - `get_conversation_context` + memória por `titular_id` (R-03 + R-12)

- Status: Approved (2026-05-31)
- Versão alvo: 1.5.0 (a memória proativa passa a ser legível pelo agente via tool MCP)
- ADRs: **ADR-0005 (revisão no mesmo PR)** — a injeção de memória prometida deixa de
  ser "no backend que injeta o turno" e passa a ser cumprida por uma **tool MCP read-only**.
  ADR-0012 (auditoria por tool-call) cobre a nova tool sem mudança de mecanismo.
- Itens do roadmap: **R-03** (tool de memória legível) **+ R-12** (chave por `titular_id`,
  acoplado na mesma SPEC para a tool já consumir a chave correta).

## 1. Problema

O ADR-0005 prometia que o contexto gravado em `conversation_memory` (pagamento confirmado,
interrupção aberta/encerrada, último protocolo) chegaria ao agente "pela entrada confiável do
canal", lido no backend e **injetado** no turno. Essa injeção **nunca foi implementada**: o
spawn do agente só passa o `AGENTS.md` estático. Resultado: a **escrita** da memória é
determinística e correta (worker/`ProactiveService`), mas o agente **não lê** nada — não há
tool MCP de memória. O loop proativo↔reativo fica aberto: o cliente recebe "sua fatura foi
paga" pelo fluxo proativo e, no turno seguinte, o agente reoferece a 2ª via da mesma fatura.

Além disso, a memória é chaveada por `chat_id == telefone E.164` (`EventoCX.chat_id` retorna
`self.telefone`; `ProactiveService.processar` grava com `chat_id=evento.chat_id`). Isso
fragmenta o contexto quando o titular tem **múltiplas UCs** (SPEC-013) ou liga de **número
diferente / LID** (SPEC-015). A chave correta é `titular_id` (R-12).

## 2. Objetivo

1. **R-03:** uma 10ª tool MCP **read-only** `get_conversation_context(phone)` que resolve o
   titular pelo telefone do remetente e devolve os **fatos canônicos recentes** já gravados,
   sob o **mesmo guardrail de acesso por telefone** das demais tools. O agente a chama no
   **abrir** da conversa (junto de `find_customer_by_phone`) para não repetir o que já foi
   resolvido.
2. **R-12 (acoplado):** especificar a migração da chave de memória para `titular_id`, de modo
   que a tool já consuma a chave correta, **sem quebrar** o `/{chat_id}/memory` legado (o
   console do operador lê por chat).

## 3. Contrato da tool

```python
get_conversation_context(phone: str) -> dict[str, Any]
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
  Itens **ordenados do mais recente para o mais antigo** e **truncados nas últimas N=10**.
  `N` é default da tool (`_MEMORIA_LIMITE`), **não** input do agente. Cada item corresponde a
  uma linha de `conversation_memory` gravada deterministicamente pelo `ProactiveService`/worker
  (ex.: `proativo.pagamento.confirmado`, `proativo.outage.encerrada`).
- **Telefone não resolve titular:** `{"encontrado": false, "motivo": "Telefone nao identificado."}`
  (mesmo formato das demais tools) — e a memória **não** é consultada.
- **Read-only:** não escreve, não muta estado.

## 4. Guardrail (determinístico, no código — não no prompt)

1. Resolve o titular **sempre** pelo `phone` do remetente (contexto confiável injetado pelo
   canal/Omni), **nunca** por id/telefone citado pelo cliente (não contornável por injection).
2. Se não resolve titular → `{"encontrado": false}` e **não** consulta memória.
3. Lê **apenas** a memória do chat do próprio titular. Como a memória é chaveada por
   `chat_id == telefone E.164` (ADR-0005), a tool usa o **telefone canônico normalizado**
   (`variantes_nono_digito` sobre `normalizar_msisdn`, SPEC-015), **nunca** o telefone cru
   recebido. Para na primeira variante com memória.
4. Auditada por `AuditedCxTools` como as demais (ADR-0012): log estruturado + sink best-effort,
   PII mascarada (`phone` → sufixo de 4 dígitos).

## 5. Escopo

### MCP (R-03 — entregue nesta SPEC)
- `ports.py`: `LegacyApiClient` += `get_conversation_memory(chat: str, limit: int = 10) -> list[dict]`.
- `client.py`: `HttpxLegacyApiClient.get_conversation_memory` → `GET /conversations/{chat}/memory`
  (envia `?limit=` por cortesia; a truncagem definitiva é no CxTools, o router legado pode
  ignorar o parâmetro sem quebrar).
- `tools.py`: `CxTools.get_conversation_context(phone)` + helper privado
  `_ler_memoria_do_titular(phone)` (resolve variantes canônicas, ordena, trunca em N=10).
- `audit.py`: `AuditedCxTools.get_conversation_context` (espelha a superfície, instrumentada).
- `server.py`: 10ª `@mcp.tool() get_conversation_context` (registrada **por último** → ordem
  estável para a allowlist do R-02 / cache R-07).
- Allowlist (R-02, fonte única `src/interfaces/mcp/allowlist.py`): a tool entra como 10º nome,
  habilitada em **produção** (frontmatter) e nos **evals** (`run.py`), com **teste de paridade**
  que impede drift.

### REST (reúso, R-03 puro)
- **Sem endpoint novo** para R-03: reúsa `GET /conversations/{chat_id}/memory`
  (`src/interfaces/rest/routers/conversation.py:14`, `response_model=list[MemoryItemDTO]`
  → `[{chave, valor, atualizado_em}]`). O `chat_id` é o telefone.
- Desejável (barato, opcional): aceitar `?limit=` no router e em `MemoryService.get` para
  truncar no servidor. Enquanto não houver, a truncagem ocorre no CxTools.

### R-12 (acoplado — chave por `titular_id`)
- Migração Alembic: `conversation_memory` reindexada por `titular_id` (resolvido via
  `BillingService.find_customer_by_phone`), mantendo `chat_id` como **chave secundária** para
  registros sem `titular_id` resolvível (fallback idempotente).
- `MemoriaRepository.list_for_titular(titular_id)` + `MemoryService.get_por_titular`.
- **Endpoint novo:** `GET /conversations/by-titular/{titular_id}/memory` (mesmo
  `response_model`), **sem quebrar** `/{chat_id}/memory` (console por chat).
- A tool migra **por dentro**: `_ler_memoria_do_titular` passa a chamar
  `get_conversation_memory_by_titular(titular_id)` — **a assinatura e o retorno externos da
  tool não mudam** (`get_conversation_context(phone) -> mesmo dict`). Só muda o adapter REST.

## 6. Fora de escopo

- Memória semântica de longo prazo / recall por similaridade (R-15).
- Resumo/compactação da memória por LLM (R-08/R-15).
- Escrita de memória pela tool (a tool é read-only; a escrita continua 100% determinística no
  worker/`ProactiveService`).

## 7. Plano TDD

1. **Port/adapter** (unit): `get_conversation_memory` faz `GET` com `?limit=` e devolve a lista.
2. **Tool** (unit, fakes):
   - retorna o contexto do titular (chaves canônicas presentes);
   - itens do mais recente para o mais antigo;
   - telefone desconhecido → `encontrado=false` e **não** consulta memória;
   - **não vaza** memória de outro titular (Carlos não recebe a memória da Ana);
   - best-effort sem memória (itens vazios, sem quebrar).
3. **Paridade (R-02)** `tests/unit/test_mcp_allowlist_parity.py`: `get_conversation_context`
   presente nas 3 fontes (server, eval-scope, frontmatter); server == allowlist em conjunto.
4. **Contagem:** `server.py` passa a registrar **10** `@mcp.tool()`.
5. **R-12:** migração idempotente + endpoint `by-titular` + repo `list_for_titular`, com
   fallback para `chat_id`; suite de regressão verde (console por chat segue funcionando).

## 8. Critérios de aceite

- No 1º turno, o agente chama `find_customer_by_phone` **e** `get_conversation_context` e
  **não** reoferece a 2ª via de uma fatura já marcada como paga na memória.
- Guardrail: telefone sem titular → `encontrado=false`, **sem** leitura de memória; a tool
  jamais devolve memória de chat que não seja do titular resolvido.
- A tool aparece em **produção** (frontmatter) **e** nos **evals**, e o teste de paridade
  bloqueia drift (cobre R-02 + R-03).
- R-12: memória chaveada por `titular_id` com fallback `chat_id`; assinatura/retorno externos
  da tool inalterados.
- unit + api + integration + lint/typecheck verdes.

## 9. Notas

- A tool **não** precisa de endpoint novo para R-03 puro porque `chat_id == telefone`. O
  endpoint `by-titular` só entra com R-12 e é aditivo.
- Ordem de registro em `server.py` = ordem em `allowlist.TOOL_NAMES` = ordem em `run.py`:
  pré-requisito de prompt caching (R-07) e contrato do teste de paridade.
