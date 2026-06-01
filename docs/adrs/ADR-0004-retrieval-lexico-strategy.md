# ADR-0004 - Retrieval lexico com Strategy plugavel (revisado: comparativo de estrategias)

- Status: Accepted
- Data: 2026-05-30
- Revisao: 2026-05-31 (R-14, `docs/11-roadmap-melhorias-agente.md`). Adicionada a secao
  **"Comparativo de estrategias de retrieval"** (RAG-lexico x CAG x pgvector x Graph RAG/RLM),
  que era o item de vaga Lead "retrieval comparado". A **decisao de MVP permanece a mesma**
  (retrieval lexico no filesystem atras de um Strategy); a revisao apenas torna **explicita e
  justificada** a escolha de nao-fazer as alternativas avancadas nesta escala, e nomeia o
  gatilho de migracao. Optou-se por **fundir no ADR-0004** em vez de abrir um ADR-0015 autonomo,
  para reduzir a superficie documental (ja sao 13 ADRs) — a decisao de retrieval continua **uma
  so**. A estrategia **CAG** referida aqui e a mesma do ADR-0014 (R-08).

## Context

O agente precisa responder duvidas ("como faco para...") fundamentado numa base de conhecimento (KB) - isto e RAG (geracao ancorada em conteudo recuperado). A KB do dominio e pequena (dezenas de artigos). Busca vetorial (embeddings) brilha em escala; para corpus pequeno, busca lexica ou ate carregar a KB no contexto (CAG) costuma performar igual ou melhor, sem dependencia paga.

As vagas valorizam **escolher a estrategia de retrieval por caso** (RAG, CAG, Graph RAG, RLM, filesystem).

## Decision

MVP usa **retrieval lexico no filesystem**: a KB e o conjunto de markdown em `kb/` (fonte unica de verdade) e a busca e em processo (scan + ranking lexico), sem ingestao em banco. E a estrategia "filesystem" que as vagas citam - a mais simples e reproduzivel para uma KB pequena. O retrieval fica atras de um **Strategy** (`KnowledgeRetrievalPort`), permitindo trocar a implementacao sem tocar no caso de uso. O agente so afirma o que veio nos trechos recuperados e cita o `slug` da fonte (guardrail anti-alucinacao).

A divisao correta e por **tipo de dado**, nao cascata: dados estruturados (clientes, faturas, outages) vivem no Postgres e sao consultados pelas ferramentas transacionais; a KB nao-estruturada vive no filesystem. Nao ha fallback "busca no banco senao no filesystem" para a KB.

## Consequences

Positivas:
- Reprodutivel, explicavel e citavel; sem credencial paga no caminho critico (alinhado ao threat model).
- Strategy permite evoluir e comparar abordagens nos evals.

Negativas:
- Busca lexica nao captura sinonimia tao bem quanto semantica; e o scan em processo nao escala para milhares de docs. Aceitavel para KB pequena e curada.

## Comparativo de estrategias de retrieval (revisao 2026-05-31, R-14)

A decisao de senioridade Lead nao e "usar a tecnica mais sofisticada", e **escolher a estrategia
certa para a escala e justificar o que se deixa de fora**. A KB da Luz do Vale tem **6 verbetes /
~3,5 KB / 79 linhas** (corpus pequeno, curado, de baixa rotatividade). Sob esse perfil:

| Estrategia | O que e | Custo/dependencia | Cabe na escala atual? | Decisao |
|---|---|---|---|---|
| **RAG-lexico (filesystem)** | scan + ranking lexico sobre `kb/*.md` em processo, atras do `KnowledgeRetrievalPort` | nenhuma credencial; 1 ida-e-volta MCP por consulta | sim | **MVP (atual)** — reproduzivel, citavel, sem custo |
| **CAG (Cache-Augmented Generation)** | carregar a KB **inteira** no system prompt cacheado (`cache_control`); sem tool no caminho critico | nenhuma credencial; ~3,5 KB cacheados por turno | sim, e otimo nesta escala | **Recomendado (R-08/ADR-0014)** — corta o hop de busca e o risco da query errar o artigo; `search_knowledge_base` fica como fallback |
| **RAG-semantico (pgvector + embeddings)** | embeddings (local, ex. sentence-transformers) + busca vetorial + rerank | infra de vetor + modelo de embedding; sem API paga | **overkill** a 3,5 KB; ganho real so com centenas/milhares de docs | **Pos-MVP** — vira estrategia atras do mesmo port quando a KB crescer (gatilho abaixo) |
| **Graph RAG** | grafo de entidades/relacoes + recuperacao por caminho | construcao e manutencao de grafo de conhecimento | **nao** — KB de FAQ sem grafo de entidades natural | **Rejeitado** (nesta escala) — manutencao do grafo > beneficio |
| **RLM / filesystem-as-context** | tratar o `kb/` como contexto navegavel pelo proprio modelo | nenhuma | parcial — e o que CAG/lexico ja exploram | **Subsumido** por CAG (KB inteira no contexto) + `kb/` como fonte unica |

**Conclusao da comparacao.** Para a escala atual, o ponto otimo e **CAG** (KB inteira no prefixo
cacheado, ADR-0014/R-08) com **RAG-lexico como fallback** para perguntas fora dos verbetes
carregados — ambos sem credencial paga no caminho critico. As tecnicas avancadas
(pgvector/embeddings, Graph RAG) sao **deliberadamente nao-implementadas**: o sinal de engenharia
vem de **decidir e justificar**, nao de pagar complexidade que a escala nao pede.

**Gatilho de migracao para RAG-semantico (pgvector):** quando a KB ultrapassar a ordem de **algumas
dezenas de artigos** (ou passar a sofrer com sinonimia/parafrase que o lexico erra de forma medivel
nos evals), troca-se a estrategia **por tras do mesmo `KnowledgeRetrievalPort`**, sem tocar o use
case — exatamente o que o Strategy existe para permitir. Graph RAG so entraria se o dominio
ganhasse um grafo de entidades/relacoes real (nao e o caso de um FAQ de utility).

## Alternatives

- **Cascata "banco senao filesystem" para a KB**: rejeitada. Seriam duas implementacoes da mesma busca, com fonte de verdade duplicada e um fallback que raramente roda (e apodrece). Strategy serve para **trocar**, nao para cascatear.
- **Postgres full-text para a KB**: alternativa valida; vira estrategia opcional atras do mesmo port se quisermos ranking/escala. Nao necessaria no MVP.
- **Embeddings + vetor (pgvector)**: **pos-MVP**. RAG misto (semantico + lexico) com **modelo de embedding local** (sentence-transformers) + rerank, so apos o vertical slice verde - sem API paga.
- **Embeddings pagos no caminho critico**: rejeitado (custo + risco de credencial).
