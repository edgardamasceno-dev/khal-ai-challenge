# SPEC-027 - Memoria de conversa chaveada por `titular_id` (sem quebrar `get_account_events`)

- Status: Approved (2026-05-31)
- Versao alvo: 1.7.0 (a `conversation_memory` deixa de fragmentar por `chat_id` e passa a ser lida
  pelo titular inteiro)
- Item do roadmap: **R-12** (`docs/11-roadmap-melhorias-agente.md §3.1, §4.2 R-12`).
- ADRs: **ADR-0005** (eventos deterministicos alimentando a memoria — a **chave** da memoria muda
  para `titular_id`, como o proprio ADR-0005 ja antecipa na revisao 2026-05-31), **ADR-0013**
  (fronteira de memoria — `get_account_events` le os eventos de sistema; esta SPEC so muda a
  **chave** sem mudar a tool), **ADR-0017** (ACL via MCP-over-REST — a troca de chave e absorvida
  **inteiramente no backend**; o contrato MCP-over-REST `GET /conversations/{chat}/memory`
  permanece). Relaciona-se com SPEC-013 (multi-UC) e SPEC-015 (LID vs. MSISDN), cuja fragmentacao
  esta SPEC corrige.

## 1. Problema

A `conversation_memory` e chaveada por `chat_id` (telefone): `UNIQUE(chat_id, chave)` e o upsert
gravam **so** `(chat_id, chave)`. Isso **fragmenta** a memoria quando o titular tem multiplas UCs
ou liga de numero diferente / via LID em vez de MSISDN (SPEC-013/SPEC-015): o mesmo titular vira
varios "chats" e o agente perde fatos gravados sob outra variante. A tabela **ja** tem a coluna
`titular_id uuid REFERENCES titulares(id)` (`db/init/01-schema.sql`, `MemoriaORM`), porem **nunca
populada** — a chave correta existe no schema mas nao e usada.

**Ponto-chave (RISCO 2 do contrato):** a tool MCP `get_account_events(phone)` e o
`LegacyApiClient.get_conversation_memory` **NAO mudam de assinatura**. A troca de chave e absorvida
**inteiramente no backend**; o contrato MCP-over-REST (`GET /conversations/{chat}/memory`)
permanece, mas internamente **resolve telefone → titular** e le **por titular**.

## 2. Objetivo

Popular `conversation_memory.titular_id` na **escrita** e ler **por titular** na **leitura**, de
forma que a **mesma URL** `GET /conversations/{phone}/memory` passe a devolver os eventos do
**titular inteiro** (des-fragmentado), **sem** mudar a tool MCP nem o port `LegacyApiClient`. O
teste de contrato de `get_account_events` (cluster MCP) deve continuar **verde sem edicao** — e a
prova de que a tool nao quebrou.

## 3. Design (todo no cluster backend; arquivos disjuntos do cluster MCP)

### 3.1 Escrita popula `titular_id`
`ProactiveService.processar` e `.disparar_por_telefone` ja resolvem o titular (`find_by_phone`) —
**propagar `titular.id`** para o upsert. Estender:
- `application/ports.py` `MemoriaRepository.upsert(chat_id, chave, valor, titular_id: uuid.UUID | None = None)`
  — default `None` preserva back-compat dos callers que ainda nao resolvem titular.
- `infrastructure/repositories.py` `SqlMemoriaRepository.upsert` grava o `titular_id`.
- `application/services.py` `MemoryService.put` ganha `titular_id` opcional.

### 3.2 Leitura por titular
- `application/ports.py` `MemoriaRepository.list_for_titular(titular_id) -> list[...]`.
- `infrastructure/repositories.py` `SqlMemoriaRepository.list_for_titular`
  (`SELECT ... WHERE titular_id = :tid ORDER BY chave`).
- `application/services.py` `MemoryService.get_for_titular(titular_id)`.

### 3.3 Compat na borda REST (o que mantem `get_account_events` funcionando)
No router `conversation.py`, `get_memory(chat_id)` passa a:
1. **Resolver o titular** pelas variantes do 9o digito (`BillingService.find_customer_by_phone`, ja
   tolerante a LID/MSISDN).
2. Se **resolveu** titular → retornar **UNIAO** de `list_for_titular(titular.id)` +
   `list_for_chat(chat_id)`, **deduplicada por `chave`** (preferindo o registro **com**
   `titular_id`) — cobre registros legados sem `titular_id` **e** os multi-UC/LID fragmentados que
   R-12 corrige.
3. Se **nao** resolveu titular → **fallback puro** `list_for_chat(chat_id)` (comportamento atual).

Assim a **mesma URL** `/conversations/{phone}/memory` devolve agora os eventos do titular inteiro,
e o MCP `get_account_events` (que ja itera variantes do 9o digito em
`CxTools._ler_eventos_do_titular`) continua **identico** — e ate melhora (menos fragmentacao).
**Nenhuma** alteracao em `src/interfaces/mcp/*`.

### 3.4 Migracao / backfill (idempotente, sem alembic no repo → via db/init + script)
- **DDL:** a coluna ja existe; manter `UNIQUE(chat_id, chave)` (idempotencia de escrita por chat
  preservada) e **adicionar indice nao-unico** em `(titular_id)` para a leitura
  (`db/init/01-schema.sql`).
- **Backfill deterministico e reexecutavel:**
  `UPDATE conversation_memory m SET titular_id = t.id FROM titulares t WHERE m.titular_id IS NULL
  AND m.chat_id IN (<variantes do telefone_principal de t>)` — empacotado como **funcao Python
  idempotente** (rodavel no boot/seed e no CI). Registros cujo `chat_id` nao casa nenhum titular
  ficam com `titular_id NULL` e seguem lidos por `list_for_chat` (fallback do §3.3).

## 4. Guardrail / compat

- **Chave primaria logica** vira `titular_id`; `chat_id` vira **chave secundaria/legada**.
- A tool MCP e o port `LegacyApiClient` ficam **imutaveis**; **nenhuma mudanca observavel** no
  contrato externo do agente.
- Resolucao do titular na borda REST usa o mesmo `find_customer_by_phone` tolerante a LID/MSISDN —
  o guardrail de acesso-so-ao-titular continua **identico** (resolvido pelo telefone do remetente).
- Telefone desconhecido na borda → fallback `list_for_chat` (nao quebra; nao vaza outro titular).

## 5. Escopo

### Backend (entregue nesta SPEC)
- `src/application/ports.py`: `MemoriaRepository.upsert(... titular_id=None)` + `list_for_titular`.
- `src/infrastructure/repositories.py`: `SqlMemoriaRepository` grava `titular_id` + `list_for_titular`
  + funcao de **backfill idempotente**.
- `src/application/services.py`: `MemoryService.put(... titular_id)` + `get_for_titular`;
  `ProactiveService` propaga `titular.id` no upsert.
- `src/infrastructure/orm.py`: `MemoriaORM` ja tem `titular_id`; so ajuste/indice se necessario.
- `src/interfaces/rest/routers/conversation.py`: `get_memory` resolve titular e une
  `list_for_titular` + `list_for_chat` (dedup por `chave`).
- `db/init/01-schema.sql`: indice nao-unico em `conversation_memory.titular_id` (coluna ja existe).

### Cluster MCP — **nao tocado**
- `src/interfaces/mcp/*` **inalterado**. `get_account_events` e `LegacyApiClient.get_conversation_memory`
  imutaveis. A regressao de contrato e justamente o teste da tool rodando **sem edicao**.

## 6. Fora de escopo

- **Alembic/migration framework:** nao ha alembic no repo; o backfill e via `db/init` + funcao
  Python idempotente.
- **Remover `chat_id`** da tabela ou do `UNIQUE`: nao — `chat_id` continua como chave secundaria
  (idempotencia de escrita por chat + fallback de leitura).
- **Mudar a assinatura/retorno** de `get_account_events` ou do `LegacyApiClient`: proibido (o ponto
  da SPEC e justamente nao mudar).
- **`get_chat_history`** (transcricao): nao toca — fonte distinta (Omni), ADR-0013.

## 7. Plano TDD

1. **Escrita (integration, `test_repositories.py`):** `upsert(... titular_id=X)` grava o
   `titular_id`; default `None` preserva back-compat.
2. **Leitura por titular (integration):** `list_for_titular(X)` retorna os registros do titular X
   ordenados por `chave`.
3. **Backfill idempotente (integration):** rodar o backfill **duas vezes** popula `titular_id` uma
   vez e nao altera registros sem titular casavel (ficam `NULL`); reexecucao e no-op.
4. **Router (api):** `GET /conversations/{phone}/memory` para telefone com titular devolve a
   **uniao** `titular + chat` deduplicada por `chave` (preferindo `titular_id`); para telefone
   **desconhecido** cai no fallback `list_for_chat` e **nao quebra**.
5. **Proactive (`test_proactive*.py`):** `processar`/`disparar_por_telefone` populam `titular_id`
   no upsert.
6. **REGRESSAO obrigatoria (cluster MCP):** `tests/unit/test_mcp_tools.py` (contrato de
   `get_account_events`) roda **verde sem edicao** — prova de que a tool nao quebrou.

## 8. Criterios de aceite

- A escrita de memoria (proativos) popula `conversation_memory.titular_id`; o default `None`
  preserva callers legados.
- `GET /conversations/{phone}/memory` devolve a **uniao** dos eventos do titular (por `titular_id`)
  + os legados por `chat_id`, deduplicada por `chave`; telefone desconhecido cai no fallback sem
  quebrar.
- O backfill e **idempotente** e reexecutavel (boot/CI), sem PII real.
- A tool MCP `get_account_events` e o `LegacyApiClient` ficam **imutaveis**; o teste de contrato da
  tool passa **sem edicao** (regressao verde) — prova de que a fronteira foi respeitada.
- unit + api + integration + lint/typecheck verdes.

## 9. Notas

- **Recomendacao do contrato:** R-12 pode entrar como **secao da SPEC-026** ou da SPEC-022
  revisada; numero proprio (esta SPEC-027) so se virar **PR separado**. Mantido como SPEC-027 para
  isolar a mudanca de chave de memoria do lembrete (SPEC-026) e da tool (SPEC-022), com fronteira
  de cluster limpa (RISCO 2 do contrato).
- **Fronteira de cluster (RISCO 2):** backend muda a borda REST por dentro; MCP consome a **mesma
  URL** via `LegacyApiClient` (imutavel). Backend **nao** toca `src/interfaces/mcp/*`; MCP **nao**
  toca `services.py`/`repositories.py`/`conversation.py`.
- **Ordem no cluster backend (RISCO 3):** R-12 (assinatura do `upsert`) **primeiro**; depois R-16
  (SPEC-026), que grava a memoria do lembrete ja com `titular_id`.
