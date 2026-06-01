# ADR-0014 - Token/Context Optimization (guarda-chuva: prompt caching + CAG + selecao de modelo por caso)

- Status: Accepted (decisão 2026-05-31; **seção de Implementação** Onda C 2026-05-31, R-07/R-08/R-09)
- Data: 2026-05-31
- Item do roadmap: R-06 (decisão) + R-07/R-08/R-09 (implementação, `docs/11-roadmap-melhorias-agente.md`).
- Relaciona-se com: ADR-0004 (retrieval lexico — a estrategia CAG estende o mesmo
  `KnowledgeRetrievalPort`), ADR-0007 (runtime Claude Code via Genie — onde o caching/modelo
  sao cabeados), ADR-0012 (auditoria — os contadores `cache_read/write_tokens` por turno sao a
  evidencia de hit-rate), ADR-0013 (fronteira de memoria — o que entra no prefixo estavel).
- Escopo: **DECISAO documentada** (corpo original, imutavel) **+ secao de Implementacao**
  (Onda C, abaixo de "Consequences"). A direcao continua unica; a implementacao de R-07
  (prefixo cacheavel), R-08 (CAG da KB) e R-09 (roteador de modelo) e detalhada na nova secao
  **"Implementacao (Onda C — R-07/R-08/R-09)"** — wiring de montagem do prompt, `--settings`/
  `cache_control` e `--model`. R-15 (`summarize_thread`) sai do guarda-chuva e ganha SPEC e ADR
  proprios (**SPEC-028 / ADR-0019**); aqui permanece so como **nota** de compressao.

## Context

"Token/context optimization (caching, compressao e escolha de modelo por caso)" e uma
responsabilidade **nominal** das vagas Senior e Lead (`docs/01`, `docs/06`). Hoje o wiring do
agente **nao** otimiza nada disso (confirmado no recon de `docs/11 §4`): nao ha `cache_control`
em lugar nenhum, o `AGENTS.md` (~56 linhas) + o catalogo de **11 tool-defs** do FastMCP sao
reenviados a cada turno, a KB (`kb/`, ~3,5 KB / 6 verbetes) e buscada por uma ida-e-volta ao MCP
mesmo quando caberia inteira no contexto, e o spawn **nao passa `--model`** — todo turno corre no
modelo default, inclusive uma saudacao.

O risco e tratar essas tres alavancas como features soltas e acabar com decisoes incoerentes
(ex.: cachear um prefixo cuja ordem de tools muda a cada deploy, invalidando o cache). Falta uma
**decisao guarda-chuva** que: (a) defina o que e prefixo cacheavel estavel; (b) escolha CAG vs.
RAG por escala de KB; (c) fixe a politica de modelo-por-caso; e (d) declare como a economia e
**provada** (nao afirmada).

## Decision

Adotar **uma estrategia unica de otimizacao de token/contexto** com tres pilares, todos
**deterministicos** e mensuraveis, sem hop de LLM adicional no caminho critico:

1. **Prompt caching estrutural (R-07).** Marcar como **prefixo cacheavel** (`cache_control`) a
   parte estavel do system prompt — `AGENTS.md` + o catalogo das 11 tool-defs — via `--settings`
   por agente (`buildClaudeCommand` ja aceita). **Pre-requisito travado:** a **ordem estavel** das
   tools, garantida pela fonte unica `src/interfaces/mcp/allowlist.py` (R-02) e pelo teste de
   paridade; mudar a ordem invalida o cache, por isso a ordem e contrato. O ganho dominante e o
   **catalogo de tool-defs** reenviado todo turno, nao o `AGENTS.md`.

2. **CAG da KB no prefixo (R-08), atras do mesmo Strategy.** Para uma KB de **6 verbetes /
   ~3,5 KB**, carregar a KB **inteira** no system prompt cacheado custa menos que uma tool-call de
   busca (latencia + tokens de schema + risco de a query errar o artigo). Implementa-se como uma
   **nova estrategia** `CachedFullKbStrategy` por tras do `KnowledgeRetrievalPort` (ADR-0004) — sem
   tocar o use case. `search_knowledge_base` **permanece como fallback** para perguntas fora dos
   verbetes carregados. A escolha CAG vs. RAG-lexico vs. pgvector e detalhada no **ADR-0004
   revisado** (R-14).

3. **Selecao de modelo por caso (R-09), roteamento determinístico.** Roteamento por
   intencao via keyword/regex **no bridge** → `--model` (mecanismo pronto: `buildClaudeCommand`
   aceita `extraArgs`). Politica:
   - **Sonnet** = default seguro (transacional: fatura, outage, ticket).
   - **Haiku** = saudacao / FAQ de KB (barato, alto volume).
   - **Opus** = ambiguo / handoff / disputa (raro, alto valor).
   Um **pre-classificador LLM** (Haiku) e **fase 2 explicitamente adiada**: so entra se os evals
   provarem que a heuristica erra o tier — para nao adicionar um hop ao hot path (resolucao da
   Tensao 3 da mesa, `docs/11 §2`).

4. **Compressao via `summarize_thread` (R-15, nota).** No fechamento de ticket/handoff, um resumo
   barato (Haiku) grava `kind=resumo` na store, encurtando o contexto reidratado em turnos
   futuros. **Fallback obrigatorio:** falha do resumo nunca bloqueia o fechamento do ticket.

**Prova de economia (criterio de aceite da decisao).** O painel do Genie ja le
`cache_read_tokens` / `cache_write_tokens` por turno; o `tool_call_audit` (ADR-0012) ja registra
latencia por tool-call. A economia e demonstrada por **hit-rate de cache** e **custo/latencia por
tier** medidos nos evals (M-08, com `expected_model` por cenario) — nao por afirmacao no texto.

## Consequences

Positivas:
- Materializa as tres palavras-chave literais da vaga (caching, CAG/compressao, modelo-por-caso)
  como **uma decisao coerente**, nao quatro features desconexas.
- CAG fecha **caching e retrieval** na mesma jogada para a escala atual, sem credencial paga no
  caminho critico (coerente com o threat model e com ADR-0004).
- Roteamento de modelo deterministico nao adiciona latencia de classificacao; o default Sonnet e
  o piso seguro.
- A economia e **auditavel** (cache tokens + latencia por tier), nao retorica.

Negativas / trade-offs:
- O caching acopla-se a **ordem estavel** das tool-defs: qualquer reordenacao invalida o cache —
  mitigado pela allowlist como fonte unica (R-02) + teste de paridade.
- CAG **infla** o prefixo de todo turno com a KB; a ~3,5 KB cacheados e irrelevante, mas a decisao
  **nao escala** para KB grande — dai o fallback lexico permanecer e o ADR-0004 revisado definir o
  gatilho de migracao para pgvector.
- A heuristica de modelo pode **errar o tier** em casos ambiguos; mitigado por default Sonnet
  (seguro) e medicao por eval; o pre-classificador fica como fase 2.
- Paridade eval↔producao do prompt (M-07) e **pre-requisito**: cachear/CAG mexem no system prompt;
  sem o mesmo prefixo no eval e na producao, o hit-rate medido seria sinal falso.

## Implementacao (Onda C — R-07/R-08/R-09)

Esta secao registra **como** a decisao acima vira codigo na Onda C. Ela **nao** muda a decisao
(que permanece Accepted); detalha o wiring. Tres pilares, todos deterministicos e unit-testaveis
nas partes puras, com a validacao ao vivo (hit-rate de cache, spawn com `--model`) marcada como
**NOTA**.

### Ponto unico de montagem do prompt (fecha R-07 + R-08 + M-07)

Toda a otimizacao gira em torno de **uma** funcao pura de montagem, compartilhada entre eval e
producao (M-07 e pre-requisito travado: prompt divergente falsearia o hit-rate):

```python
# src/agent/prompt.py (NOVO)
def montar_system_prompt(
    agents_md: str, *, phone: str | None, kb_block: str | None
) -> str: ...
```

A funcao concatena, **nesta ordem fixa** (estavel primeiro, volatil por ultimo — pre-requisito do
cache):

1. **`AGENTS.md`** (prefixo estavel/cacheavel) — a persona + guardrails + catalogo de tools.
2. **Bloco `## Base de conhecimento (pre-carregada)`** com `kb_block` (CAG, R-08) — estavel.
3. **Bloco `## Contexto do canal`** com o telefone do remetente (sufixo **volatil**) — fora do
   prefixo cacheado.

- **`src/evals/run.py`** passa a chamar `montar_system_prompt(agents_md, phone=phone,
  kb_block=CachedFullKbStrategy(KB_DIR).dump_kb())` em vez de concatenar `AGENTS.md` + telefone
  ad-hoc (corrige o drift de montagem que `docs/11 §M-07` documenta).
- **`sandbox/genie-wire.sh`** injeta **o mesmo bloco KB** no `AGENTS.md` materializado/frontmatter,
  para que o prompt de **producao** seja byte-identico ao do eval no prefixo estavel.

**Teste (`tests/unit/test_prompt_assembly.py`):** assert que cada slug/titulo dos **6 verbetes** de
`kb/` aparece no prompt montado **e** que o prefixo (ate o bloco de telefone) e **byte-identico
entre execucoes** (idempotencia — pre-requisito de cache hit).

### R-08 — CAG da KB como estrategia sob `KnowledgeRetrievalPort` (ADR-0004)

Nova estrategia em `src/infrastructure/knowledge.py`, **sob a mesma porta** (Strategy, sem tocar o
use case):

```python
class CachedFullKbStrategy:  # implementa KnowledgeRetrievalPort
    def search(self, query: str) -> ...: ...      # fallback lexico (ADR-0004) preservado
    def dump_kb(self) -> str: ...                 # concatena os 6 verbetes (slug+titulo+corpo)
                                                  # em markdown ORDENADO por slug -> bloco cacheavel
```

`dump_kb()` reusa o `load_kb(kb_dir)` ja existente e ordena por **slug** (ordem determinística →
bloco byte-estavel → elegivel a `cache_control`). `search_knowledge_base` **permanece como
fallback** para perguntas fora dos verbetes carregados (a decisao ja previa isto). A KB de
**~3,5 KB / 6 verbetes** cabe inteira no prefixo cacheado — custa menos que uma tool-call de busca
(latencia + tokens de schema + risco de a query errar o artigo).

### R-09 — Roteador de modelo determinístico (modulo puro, sem I/O)

```python
# src/agent/model_router.py (NOVO)
class Modelo(StrEnum):
    HAIKU = "haiku"; SONNET = "sonnet"; OPUS = "opus"

def rotear_modelo(mensagem: str, *, primeiro_turno: bool = False) -> Modelo: ...
def cli_model_flag(m: Modelo) -> str: ...   # id que vai em --model
```

Heuristica keyword/regex sobre o texto **normalizado** (strip-accents + lower, reusando o
`tokenize` de `src/domain/knowledge/retrieval.py` para paridade com o retrieval lexico):

- **SONNET** = default seguro (transacional: `fatura`, `outage`, `ticket`, `2a via`).
- **HAIKU** = saudacao / FAQ curta (`oi`, `bom dia`, `como faco`, `prazo`, `bandeira`).
- **OPUS** = ambiguo / disputa / handoff (`falar com humano`, `reclamacao`, `processo`,
  `nao concordo`, `juridico`).

Sem hop de LLM (o **pre-classificador LLM e fase 2**, fora desta implementacao, so se os evals
provarem que a heuristica erra o tier — coerente com a Decisao §3).

**Consumo (wiring):**
- `src/evals/run.py` traduz `rotear_modelo(message)` → `--model cli_model_flag(...)` no comando
  `claude -p`.
- `sandbox/genie-wire.sh` le um campo `model` do frontmatter/bridge (`buildClaudeCommand` aceita
  `extraArgs`) e o passa no spawn.

**Teste (`tests/unit/test_model_router.py`):** tabela de casos `mensagem -> modelo` (saudacao →
haiku; fatura/outage/ticket → sonnet; "falar com humano"/disputa → opus). `src/evals/journeys.py`
estende `Scenario` com **`expected_model`** e o eval assere `rotear_modelo(msg) == expected_model`
(fecha M-08 para o tier de modelo).

### R-07 — Prefixo cacheavel (estrutura, nao tool nova)

O **prefixo cacheavel** e exatamente: `AGENTS.md` + catalogo das **tool-defs em ordem fixa** (fonte
unica `src/interfaces/mcp/allowlist.py`, R-02) + bloco KB (R-08), **antes** do sufixo volatil
(telefone). `montar_system_prompt` garante essa ordem; o teste de paridade prova que o prefixo e
**byte-identico** entre execucoes (pre-requisito do cache hit). O wiring de `cache_control` entra
via `--settings` por agente no `genie-wire.sh`/frontmatter (mecanismo `buildClaudeCommand` ja
pronto, ADR-0007).

> **Contrato do cache (RISCO):** a ordem das tool-defs e contrato. Se `summarize_thread` (SPEC-028)
> virasse a 13a tool MCP na `allowlist.py`, **invalidaria** o prefixo cacheado e o teste de
> paridade. Por isso SPEC-028 dispara `summarize_thread` como **servico no fechamento** (best-effort),
> **nao** como tool exposta na allowlist — preservando a ordem estavel das tools que o cache exige.

### O que e testavel agora vs. validacao ao vivo (NOTA)

| Item | Testavel neste repo (unit) | Validacao ao vivo (NOTA) |
| --- | --- | --- |
| R-07 prefixo cacheavel | prefixo byte-identico entre execucoes (`test_prompt_assembly.py`) | hit-rate real via `cache_read_tokens`/`cache_write_tokens` no painel do Genie |
| R-08 CAG da KB | os 6 verbetes de `kb/` no prompt + ordem estavel | reducao de tool-calls de busca medida nos evals (M-08) |
| R-09 roteador de modelo | tabela `msg -> modelo` + `expected_model` no eval | o `--model` chegar ao spawn do Claude Code no sandbox |

A **prova de economia** (criterio de aceite da Decisao) continua sendo hit-rate de cache + custo/
latencia por tier medidos nos evals — **nao** afirmacao no texto.

## Alternatives

- **Nao otimizar (status quo):** reenviar AGENTS.md + 11 tool-defs + buscar a KB por tool todo
  turno. Rejeitado — desperdicio nominalmente cobrado pela vaga e latencia evitavel.
- **RAG-semantico (pgvector) para a KB ja no MVP:** rejeitado por escala (3,5 KB nao justifica
  embeddings nem credencial paga); fica como pos-MVP no ADR-0004 revisado (R-14).
- **Pre-classificador LLM de modelo no hot path (fase 1):** rejeitado agora — adiciona um hop de
  LLM antes de cada turno. Adiado para fase 2, condicionado a evidencia de eval.
- **Compactacao agressiva de toda a transcricao por LLM a cada turno:** rejeitado — custo/latencia
  recorrentes e risco de perder fato relevante; preferimos resumo so no fechamento (R-15) + leitura
  tipada de eventos (ADR-0013).
- **ADRs separados por pilar (um para caching, um para CAG, um para modelo):** rejeitado — os tres
  compartilham o mesmo system prompt e os mesmos pre-requisitos (ordem estavel, paridade); separa-los
  multiplicaria a superficie documental (ja sao 13 ADRs) sem ganho de clareza.
