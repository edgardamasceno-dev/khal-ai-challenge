# SPEC-028 - Resumo de thread no fechamento de ticket/handoff (SummarizerPort + fallback extrativo)

- Status: Approved (2026-05-31)
- Versao alvo: 1.8.0 (fechar um chamado/handoff passa a registrar um **resumo** da conversa na
  `conversation_memory`, com `kind=resumo`)
- Item do roadmap: **R-15** (`docs/11-roadmap-melhorias-agente.md`, onda C).
- ADRs: **ADR-0019** (decisao: SummarizerPort + adapter Haiku opt-in + fallback extrativo
  deterministico default, gravando `kind=resumo`), **ADR-0013** (fronteira de memoria: `kind=resumo`
  e **tag no JSONB `valor`**, sem coluna nova; o resumo e mais um tipo de fato em
  `conversation_memory`, distinto da transcricao Omni e da sessao Genie), **ADR-0005** (escrita
  deterministica sem LLM no caminho critico — o **default** do resumo e o extrativo, sem rede).
  Relaciona-se com SPEC-016 (handoff), SPEC-020 (resolve+notify de ticket) e SPEC-027 (memoria por
  `titular_id`, que o upsert do resumo reaproveita).

## 1. Problema

Quando um atendimento se encerra — um **ticket resolvido** (SPEC-020) ou um **handoff devolvido a IA**
(SPEC-016) —, nada condensa **o que aconteceu** na conversa. A `conversation_memory` so guarda fatos
**deterministicos de sistema** (pagamento confirmado, outage aberta/encerrada — ADR-0005), nunca um
panorama do fio conversacional. Num cold-start (sessao Genie reseta, ADR-0013), o agente perde o
contexto do que ja foi tratado; o operador, ao reabrir a fila, nao tem um TL;DR do caso.

Resumir e uma tarefa naturalmente de LLM — mas **nao pode entrar no caminho critico** do fechamento:
o ticket precisa resolver e o cliente ser notificado **mesmo se** a API de resumo estiver fora, lenta,
ou a dep nao instalada. O desafio e ter o resumo **bom quando da** (LLM) e **sempre** um resumo
util (deterministico) sem acoplar o fechamento a uma chamada de rede.

## 2. Objetivo

Ao fechar um ticket/handoff, gravar um **resumo curto da thread** em `conversation_memory`
(`kind=resumo`), por **estrategia plugavel**: um `SummarizerPort` (LLM Haiku, **opt-in**) com
**fallback extrativo deterministico** (default, sem rede). O fechamento e **best-effort** em relacao
ao resumo: qualquer falha do resumo (LLM, persistencia, telefone ausente) **nao** propaga nem bloqueia
o `resolve_ticket`/`resume_handoff`.

## 3. Design (cluster `summarize`; arquivos disjuntos dos demais clusters da onda C)

### 3.1 Porta + erro (`src/application/ports.py`, secao final)
- `class SummarizerError(Exception)` — sinaliza ao servico para cair no fallback.
- `class SummarizerPort(Protocol)`: `summarize(mensagens: list[MensagemChat], *, max_chars=600) -> str`.
  Contrato: devolve resumo **nao-vazio** OU **levanta `SummarizerError`** (nunca string vazia
  silenciosa). `@runtime_checkable`, na **secao final** do arquivo (disjunta da `PresencePort`/R-04).

### 3.2 Fallback extrativo deterministico (DEFAULT) — `src/domain/conversation/summarize.py`
- `def resumo_extrativo(mensagens, *, max_chars=600) -> str` — **dominio puro**, sem LLM:
  seleciona a **1a mensagem do cliente** (motivo do contato) + as **ultimas N trocas** (desfecho),
  prefixa `[cliente]`/`[agente]`, normaliza espacos e trunca em `max_chars`. **Deterministico e
  idempotente** → 100% unit-testavel sem mock. Mensagens vazias → `"[sem conteudo de conversa]"`.

### 3.3 Adapter LLM Haiku (OPT-IN) — `src/infrastructure/summarize/anthropic_summarizer.py`
- `class AnthropicHaikuSummarizer(SummarizerPort)`: usa o SDK `anthropic` (Messages API, modelo
  familia Haiku — default `claude-3-5-haiku-latest`), **system prompt fixo** marcado com
  `cache_control: ephemeral` (prefixo cacheavel, ADR-0014/R-07), `timeout` curto. **Import lazy**
  do `anthropic` dentro do metodo (mesmo padrao de `minio`/`weasyprint`). **QUALQUER** excecao/empty
  → `SummarizerError`. Nao bloqueia, nao retenta.
- Dep `anthropic` e **opcional** (`[project.optional-dependencies].summarize`), com override de
  mypy (`ignore_missing_imports`). **Nunca** no caminho critico.

### 3.4 Servico orquestrador (`src/application/services.py`) — `class ThreadSummaryService`
- `__init__(transcript, memorias, titulares, uow, summarizer: SummarizerPort | None = None, clock=None, max_mensagens=50)`.
- `summarize_thread(phone, protocolo=None) -> dict`:
  1. resolve o titular (`find_by_phone_em` + variantes do 9o digito; None → grava por chat);
  2. le a transcricao (`ChatTranscriptPort.mensagens`);
  3. **estrategia**: tenta `summarizer.summarize` (se `None` **ou** levanta **ou** vazio → `resumo_extrativo`);
  4. grava via `MemoriaRepository.upsert` com `chave="resumo.<protocolo|ts>"` e
     `valor={"texto", "kind": "resumo", "fonte": "haiku"|"extrativo", "em": iso}` + `titular_id`;
  5. devolve `{"resumo", "fonte", "gravado": True}`.
- `summarize_thread_safe(phone, protocolo=None) -> None`: wrapper **best-effort** — no-op sem
  telefone; **engole qualquer excecao** (inclusive de persistencia). E o que o fechamento chama.

### 3.5 Disparo no fechamento (acoplamento best-effort, `TicketingService`)
- `TicketingService.__init__` ganha `thread_summary: ThreadSummaryService | None = None` (opt-in).
- `_resumir_thread(phone, protocolo)`: no-op sem o servico; senao chama `summarize_thread_safe`.
- `resolve_ticket` chama `_resumir_thread(titular.telefone.value, chamado.protocolo)` apos notificar.
- `resume_handoff` chama `_resumir_thread(handoff.remetente, None)` (handoff pode nao ter protocolo;
  chaveia por ts). **Nao** ha tool MCP nova: o disparo e um servico no fechamento, para **nao mexer
  na allowlist** nem invalidar o cache de tool-defs (R-07). `summarize_thread` fica disponivel como
  servico reutilizavel caso se queira expor depois.

## 4. Guardrail / compat

- **Sem LLM no caminho critico (ADR-0005):** o default e o extrativo deterministico; o LLM e opt-in,
  atras do port, e best-effort. Fechar ticket/handoff **nunca** depende de rede/dep externa.
- **`kind=resumo` e tag no JSONB `valor`** (ADR-0013): **nenhuma** coluna/entidade nova; o resumo e
  mais um fato em `conversation_memory`, lido pela mesma fronteira.
- **Idempotencia por chave** (`resumo.<protocolo|ts>`): reexecutar o fechamento do mesmo ticket faz
  **upsert** na mesma chave (nao duplica). `resolve_ticket` ja e idempotente (no-op se ja resolvido),
  entao o resumo so e (re)gravado num fechamento efetivo.
- **Memoria por `titular_id` (SPEC-027):** o upsert propaga `titular.id`; telefone desconhecido cai no
  fallback por `chat_id` (nao quebra, nao vaza outro titular).

## 5. Escopo

### Entregue nesta SPEC (cluster `summarize`)
- `src/application/ports.py`: `SummarizerError` + `SummarizerPort` (secao final, disjunta).
- `src/domain/conversation/summarize.py` (NOVO): `resumo_extrativo` (fallback deterministico).
- `src/infrastructure/summarize/anthropic_summarizer.py` (NOVO): `AnthropicHaikuSummarizer`.
- `src/application/services.py`: `ThreadSummaryService` + acoplamento best-effort em
  `resolve_ticket`/`resume_handoff` (`thread_summary` opcional no `TicketingService`).
- `tests/unit/test_thread_summary.py` (NOVO): extrativo puro, LLM sucesso/erro/None, `kind=resumo`,
  best-effort no fechamento.
- `pyproject.toml`: dep `anthropic` opcional (`[summarize]`) + override mypy.
- `docs/specs/SPEC-028-*.md` (este), `docs/adrs/ADR-0019-*.md`, indice de ADRs.

### Fora de escopo
- **Tool MCP `summarize_thread` exposta:** preferido o **disparo no servico** (nao mexe na
  allowlist/cache de tool-defs — R-07). Pode virar 13a tool numa SPEC futura.
- **Sumarizacao incremental/rolling** da janela viva (compaction de sessao): aqui e so o fechamento.
- **Outros provedores de LLM:** so o adapter Anthropic; a porta permite trocar sem tocar o servico.
- **Wiring de runtime** (injetar o `AnthropicHaikuSummarizer` no `TicketingService` real do backend):
  o default fica deterministico; habilitar o LLM e um passo de **config** posterior (ver Notas).

## 6. Plano TDD

1. **Extrativo (unit, sem mock):** determinismo/idempotencia, prefixos `[cliente]`/`[agente]`,
   `max_chars`, conteudo vazio.
2. **Servico LLM sucesso:** `FakeSummarizer` → `fonte="haiku"`, grava `kind=resumo`, `titular_id`,
   `chave="resumo.<protocolo>"`.
3. **Servico LLM falha:** `RaisingSummarizer` (levanta `SummarizerError`) → cai no extrativo
   (`fonte="extrativo"`); a falha **nao** propaga.
4. **`summarizer=None`:** usa o extrativo; resultado == `resumo_extrativo(...)`.
5. **Telefone desconhecido:** grava por `chat_id` (titular_id None), nao quebra.
6. **Best-effort:** `summarize_thread_safe` engole falha de persistencia e e no-op sem telefone.
7. **Fechamento:** `resolve_ticket`/`resume_handoff` disparam o resumo; sem `thread_summary` nao
   quebram; **falha de persistencia do resumo nao bloqueia** o fechamento.
8. **REGRESSAO:** `test_services.py` (construtor do `TicketingService`) verde sem edicao.

## 7. Criterios de aceite

- Fechar um ticket (`resolve_ticket`) ou devolver um handoff (`resume_handoff`) grava um resumo em
  `conversation_memory` com `kind=resumo` e `fonte` ∈ {`haiku`,`extrativo`}.
- Com `summarizer=None` ou falha do LLM, o resumo e o **extrativo deterministico** (sem rede).
- Falha de resumo (LLM, persistencia, telefone ausente) **nao** propaga ao fechamento.
- O resumo e idempotente por chave; respeita memoria por `titular_id` (SPEC-027).
- unit + api verdes; `ruff` e `mypy --strict` limpos. Sem mudanca na allowlist/cache de tool-defs.

## 8. Notas (validacao ao vivo / pendencias)

- **Habilitar o LLM (config, fora desta SPEC):** o backend precisa **injetar**
  `AnthropicHaikuSummarizer(...)` no `TicketingService` (composition root) + instalar
  `pip install ".[summarize]"` + ter `ANTHROPIC_API_KEY` (ou auth do Claude Code) e o **egress
  Anthropic** liberado no sandbox. **Default permanece deterministico** — nada quebra sem isso.
- **Qualidade do resumo Haiku** (vs. extrativo) so se mede **ao vivo** com transcricoes reais; o
  unit cobre o **contrato** (sucesso/erro/fallback), nao a qualidade textual do modelo.
- **Custo/latencia do hop LLM** sao reais; por isso e best-effort fora do caminho critico e o prompt
  e prefixo-estavel cacheavel (ADR-0014). O fechamento permanece deterministico e rapido.
