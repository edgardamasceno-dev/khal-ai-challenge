# SPEC-026 - Lembrete proativo de vencimento D-3/D-0 (cron deterministico, sem LLM)

- Status: Approved (2026-05-31)
- Versao alvo: 1.7.0 (a Luz do Vale passa a lembrar o cliente do vencimento da fatura, sem LLM)
- Item do roadmap: **R-16** (`docs/11-roadmap-melhorias-agente.md §3.1, §7 Onda C`).
- ADRs: **ADR-0005** (eventos deterministicos sem LLM alimentando memoria — este lembrete e um
  novo evento `utilitycx.*` que segue exatamente o fluxo de notificacao existente),
  **ADR-0013** (fronteira de memoria — o lembrete e **fato de sistema**, vai para
  `conversation_memory`/`get_account_events`, nao e transcricao). Relaciona-se com SPEC-009
  (notificacoes proativas — reusa o worker `ProactiveService`) e SPEC-027/R-12 (memoria por
  `titular_id` — o lembrete ja grava com a chave correta).

## 1. Problema

Hoje as notificacoes proativas sao **reativas a acao do operador** (baixa de pagamento,
interrupcao — SPEC-009). **Nao ha** nada que avise o cliente do **vencimento** da fatura antes
de ela vencer. Inadimplencia por esquecimento e o caso de CX mais comum de uma distribuidora; um
lembrete D-3/D-0 (3 dias antes e no dia) ataca isso preventivamente. O lembrete e **conteudo
canonico** — nao precisa (nem deve) passar por LLM (desperdicio de token + variabilidade, ADR-0005).

## 2. Objetivo

Um **cron deterministico, sem LLM**, que varre faturas com vencimento em **D-3** e **D-0** e, para
cada match elegivel, emite um evento `utilitycx.pagamento.lembrete` — que o **worker existente**
(`ProactiveService`) renderiza com template canonico, envia pelo Omni **best-effort** e grava em
`conversation_memory`. **Idempotente** por `(fatura_id, dia)`: no maximo 1 lembrete por fatura por
dia, mesmo com reexecucao do cron.

## 3. Onde roda (e onde NAO roda)

- **NAO** roda no worker de notificacao. O worker continua so consumindo `utilitycx.>` e
  notificando/gravando memoria, **igual hoje** — nao ganha logica de varredura.
- **Roda** num **novo entrypoint de backend** (que tem repos + UoW):
  `ProactiveReminderService.varrer(hoje)`, acionado por
  **`python -m src.infrastructure.events.reminder`** (cron/agendado).
- **Clock injetavel.** `hoje` e parametro (nao `date.today()` embutido), para teste determinístico.
  O calculo de D-3/D-0 usa **data local America/Sao_Paulo** (cuidado com fuso — vencimento e data
  civil, nao instante UTC).

## 4. Fluxo

1. **Varredura.** `ProactiveReminderService.varrer(hoje)` seleciona faturas `em_aberto`/`vencida`
   cujo `vencimento` cai em `hoje + 3` (D-3) ou `hoje` (D-0).
2. **Evento por match elegivel.** Para cada fatura elegivel, monta:
   ```python
   EventoCX(
       tipo="pagamento", subtipo="lembrete",
       telefone=<telefone do titular>, nome=<nome do titular>,
       idempotency_key="pagamento.lembrete.{fatura_id}.{YYYY-MM-DD}",
       dados={"fatura_id": ..., "mes": ..., "valor": ..., "vencimento": ...,
              "dias_para_vencer": 3 | 0},
   )
   ```
   `subject` derivado: `utilitycx.pagamento.lembrete`. `memoria_chave`:
   `proativo.pagamento.lembrete` (derivacao ja existente em `EventoCX`).
3. **Idempotencia por `(fatura_id, dia)`.** A `idempotency_key` inclui `{YYYY-MM-DD}`; o upsert na
   memoria usa `on_conflict_do_nothing`, garantindo **no maximo 1** lembrete por fatura por dia
   mesmo se o cron reexecutar. (D-3 e D-0 de uma mesma fatura sao **dias distintos** → chaves
   distintas → ambos disparam, cada um uma vez.)
4. **Publicacao + worker existente.** Publica em `utilitycx.pagamento.lembrete`. O
   `ProactiveService.processar` (worker existente) renderiza o **template canonico novo**
   (`render_notificacao` para subtipo `lembrete`), envia pelo Omni **best-effort** e grava em
   `conversation_memory` (com `titular_id`, SPEC-027/R-12).

## 5. Mudancas no dominio de notificacoes

- `EVENTOS_VALIDOS += ("pagamento", "lembrete")` (`src/domain/notifications/entities.py`). Com
  isso, `EventoCX` ja deriva `subject` (`utilitycx.pagamento.lembrete`) e `memoria_chave`
  (`proativo.pagamento.lembrete`) sem outra mudanca.
- **Template canonico** do lembrete em `src/domain/notifications/templates.py`, com as duas
  variantes por `dias_para_vencer`:
  - **D-3:** "Ola {nome}, sua fatura de {mes} (R$ {valor}) vence em {vencimento} — daqui a 3 dias.
    Quer a 2a via ou o PIX para pagar?"
  - **D-0:** "Ola {nome}, sua fatura de {mes} (R$ {valor}) **vence hoje** ({vencimento}). Posso te
    enviar a 2a via / PIX agora?"
  (texto canonico, sem LLM; tom e formato finais ficam para o TDD/revisao).
- `ProactiveService._executar_acao` (`src/application/services.py`): caso
  `("pagamento", "lembrete")` e **NO-OP de dominio** — o lembrete **so notifica**, **nao muta**
  estado de fatura (diferente de `confirmado`, que da baixa). Apenas renderiza + envia + grava
  memoria.

## 6. Guardrail / robustez (deterministico, sem LLM)

1. **Sem LLM no caminho.** Varredura, elegibilidade, template e idempotencia sao 100% codigo.
2. **Idempotente** por `(fatura_id, YYYY-MM-DD)` (`on_conflict_do_nothing`): reexecutar o cron no
   mesmo dia **nao** duplica lembrete.
3. **Best-effort no envio Omni.** Falha de envio nao quebra a varredura nem o registro de memoria
   (mesma fronteira best-effort do worker, ADR-0005/ADR-0012).
4. **Fuso correto.** D-3/D-0 calculados em **data local (America/Sao_Paulo)**; `hoje` injetavel.
5. **So o titular da fatura.** O telefone do evento e o do titular dono da fatura (resolvido no
   backend), nunca um telefone arbitrario.

## 7. Escopo

### Backend (entregue nesta SPEC)
- `src/domain/notifications/entities.py`: `EVENTOS_VALIDOS += ("pagamento", "lembrete")`.
- `src/domain/notifications/templates.py`: template canonico D-3/D-0.
- `src/application/services.py`: **`ProactiveReminderService`** novo (varredura + montagem do
  evento + idempotencia); `ProactiveService._executar_acao` ganha o caso `("pagamento","lembrete")`
  como **NO-OP de dominio**.
- `src/infrastructure/events/reminder.py`: **novo entrypoint**
  `python -m src.infrastructure.events.reminder` (instancia repos+UoW e chama
  `ProactiveReminderService.varrer(date local)`).
- `src/infrastructure/events/worker.py`: rota o subtipo `lembrete` pelo fluxo de notificacao
  existente (consome `utilitycx.pagamento.lembrete`).
- `src/interfaces/rest/dependencies.py`: wiring do `ProactiveReminderService` se exposto.

### Fora do backend
- **Lado MCP/tools:** nenhum. O agente **le** o lembrete via `get_account_events` (ja existe,
  SPEC-022) — o lembrete e mais um fato de sistema na `conversation_memory`. Nenhuma tool nova.

## 8. Fora de escopo

- **Lembrete via LLM** ou texto gerado: nao — canonico, ADR-0005.
- **Agendador/cron de infra** (systemd timer, k8s CronJob): fora; entregamos o **entrypoint
  invocavel** (`python -m ...`) e o gatilho fica a cargo do orquestrador/compose/CI (runbook, R-18).
- **Outros marcos** (D-7, pos-vencimento, corte iminente): nao nesta SPEC; D-3/D-0 primeiro.
- **Mudanca de estado da fatura** pelo lembrete: nao (NO-OP de dominio — so notifica).

## 9. Plano TDD

1. **Dominio (unit):** `("pagamento","lembrete")` valido em `EVENTOS_VALIDOS`; `EventoCX` deriva
   `subject=utilitycx.pagamento.lembrete` e `memoria_chave=proativo.pagamento.lembrete`. Template
   D-3 e D-0 renderizam os campos (`nome/mes/valor/vencimento/dias_para_vencer`).
2. **Varredura (unit, clock fixo):** `varrer(hoje)` seleciona faturas em D-3 e D-0 e **ignora** as
   de outros vencimentos; `idempotency_key` no formato `pagamento.lembrete.{fatura_id}.{YYYY-MM-DD}`.
3. **Idempotencia (integration, `test_repositories.py`):** rodar `varrer` **duas vezes** no mesmo
   `hoje` grava o lembrete **uma vez** (`on_conflict_do_nothing`); D-3 e D-0 da mesma fatura geram
   **dois** registros (dias distintos).
4. **Worker (unit, `test_proactive*.py`):** `ProactiveService.processar` do subtipo `lembrete`
   renderiza o template, tenta enviar Omni best-effort e grava em `conversation_memory`;
   `_executar_acao` e **NO-OP** (estado da fatura inalterado).
5. **Entrypoint (`test_reminder.py`, novo):** `python -m src.infrastructure.events.reminder` com
   clock injetavel dispara `varrer` e publica os eventos esperados (fake bus).
6. **Eval (cluster evals, M-08)** `J16-lembrete-vencimento`: persona com fatura vencendo, mensagem
   de follow-up — o agente, ao abrir, **le** o lembrete via `get_account_events` e oferece 2a
   via/PIX (assercao por tool-call).
7. **Regressao:** suite verde; SPEC-009 (notificacoes existentes) intacta.

## 10. Criterios de aceite

- O cron `python -m src.infrastructure.events.reminder` varre D-3 e D-0 (data local
  America/Sao_Paulo, clock injetavel) e emite `utilitycx.pagamento.lembrete` **sem LLM**.
- **Idempotente** por `(fatura_id, dia)`: reexecucao no mesmo dia nao duplica; D-3 e D-0 da mesma
  fatura disparam uma vez cada.
- O worker existente renderiza o template canonico, envia pelo Omni best-effort e grava em
  `conversation_memory` (com `titular_id`, SPEC-027) — e o lembrete **nao** muta o estado da fatura.
- O agente le o lembrete via `get_account_events` (sem tool nova) e age coerentemente.
- unit + api + integration + lint/typecheck verdes.

## 11. Notas

- **Reuso, nao duplicacao:** a varredura e nova; o **envio + memoria** reusam o `ProactiveService`
  e o broker (`EventBusPort`) que ja servem SPEC-009. O unico ramo novo no worker e o subtipo
  `lembrete` (NO-OP de dominio).
- **Fronteira ADR-0013:** o lembrete e **fato de sistema** (store → `get_account_events`), nao
  transcricao (`get_chat_history`). Coerente com a separacao das duas tools de leitura.
- **Ordem no cluster backend (RISCO 3 do contrato):** SPEC-027/R-12 (chave `titular_id`) entra
  **antes**, para o lembrete ja gravar a memoria com a chave correta.
