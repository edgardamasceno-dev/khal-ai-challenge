# ADR-0014 - Token/Context Optimization (guarda-chuva: prompt caching + CAG + selecao de modelo por caso)

- Status: Accepted
- Data: 2026-05-31
- Item do roadmap: R-06 (`docs/11-roadmap-melhorias-agente.md`).
- Relaciona-se com: ADR-0004 (retrieval lexico — a estrategia CAG estende o mesmo
  `KnowledgeRetrievalPort`), ADR-0007 (runtime Claude Code via Genie — onde o caching/modelo
  sao cabeados), ADR-0012 (auditoria — os contadores `cache_read/write_tokens` por turno sao a
  evidencia de hit-rate), ADR-0013 (fronteira de memoria — o que entra no prefixo estavel).
- Escopo: **DECISAO documentada**. A implementacao (wiring de `--settings`/`cache_control`,
  estrategia CAG, roteamento de modelo) fica para a **Onda C**; este ADR registra a direcao
  unica para que R-07/R-08/R-09/R-15 nao virem decisoes ad-hoc espalhadas.

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
