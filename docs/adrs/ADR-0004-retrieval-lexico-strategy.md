# ADR-0004 - Retrieval lexico com Strategy plugavel

- Status: Accepted
- Data: 2026-05-30

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

## Alternatives

- **Cascata "banco senao filesystem" para a KB**: rejeitada. Seriam duas implementacoes da mesma busca, com fonte de verdade duplicada e um fallback que raramente roda (e apodrece). Strategy serve para **trocar**, nao para cascatear.
- **Postgres full-text para a KB**: alternativa valida; vira estrategia opcional atras do mesmo port se quisermos ranking/escala. Nao necessaria no MVP.
- **Embeddings + vetor (pgvector)**: **pos-MVP**. RAG misto (semantico + lexico) com **modelo de embedding local** (sentence-transformers) + rerank, so apos o vertical slice verde - sem API paga.
- **Embeddings pagos no caminho critico**: rejeitado (custo + risco de credencial).
