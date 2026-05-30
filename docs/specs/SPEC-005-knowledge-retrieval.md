# SPEC-005 - Base de conhecimento + search_knowledge_base

- Status: Draft
- Versao alvo: 0.6.0 (RAG lexico sobre a KB)
- ADRs: ADR-0004 (retrieval lexico com Strategy), ADR-0001 (Python). **Nenhum ADR novo.**

## 1. Problema

O agente precisa responder duvidas ("como faco para...") fundamentado numa base de
conhecimento, **citando a fonte** (RF-08). Hoje a tool `search_knowledge_base` nao existe e
nao ha corpus `kb/`.

## 2. Objetivo

Implementar a KB e a tool, **deterministicamente** (sem embeddings/pago), conforme ADR-0004:
corpus markdown em `kb/`, retrieval lexico em processo atras do `KnowledgeRetrievalPort`
(Strategy), exposto por REST, e a tool MCP que o agente usa citando o `slug`.

### Decisao de arquitetura (pinada aqui; nao contraria ADR)
O retrieval roda **no backend** (`KnowledgeRetrievalPort` + adapter filesystem lexico),
exposto por `GET /api/kb/search`. A tool MCP `search_knowledge_base` e um **wrapper** que
chama esse REST (consistente com o MCP-over-REST, SPEC-003). O corpus `kb/` entra na imagem
do backend. A divisao por **tipo de dado** (estruturado no Postgres; KB nao-estruturada no
filesystem) segue o ADR-0004 - sem cascata banco/filesystem.

## 3. Escopo

- `kb/*.md`: corpus (frontmatter `titulo`/`tags` + corpo; `slug` = nome do arquivo).
- Dominio Knowledge: `Artigo`, `ResultadoKB`, e o ranking **lexico puro** (tokenize + score
  com boost de titulo/tags + extracao de trecho).
- `KnowledgeRetrievalPort` (application) + `FilesystemKnowledgeRetrieval` (infra: loader + ranking).
- REST `GET /api/kb/search?q=&limit=` -> lista de `{slug, titulo, trecho, score}`.
- Tool MCP `search_knowledge_base(query)` (wrapper sobre o REST) + atualizacao do `agent/AGENTS.md`.
- Harness: jornada **J8** + assercoes determinISticas.

## 4. Fora de escopo

- Embeddings/pgvector e Postgres FTS (pos-MVP, ADR-0004).
- **LLM-as-judge / Agent Score** (faltam dimensoes subjetivas; vira SPEC propria). Aqui a
  validacao do agente e **determinISTICA**: chamou a tool? citou o slug? a resposta ancorou
  no trecho recuperado?

## 5. Criterios de aceite

- Retrieval lexico: query relevante retorna o artigo correto no topo; query sem match -> vazio.
- `GET /api/kb/search?q=religacao` retorna o artigo de religacao com `slug` e `trecho`.
- Tool MCP `search_knowledge_base` devolve resultados com `slug`.
- Agente (J8): chama `search_knowledge_base`, **cita o slug** e responde ancorado no trecho.
- Suite anterior verde; ruff e mypy estrito limpos.

## 6. Plano de testes

- **TDD (unit, deterministico)**: tokenize/rank (ranking, boost, trecho, sem match); loader de
  `kb/` (frontmatter + slug); endpoint REST (TestClient + port fake); tool MCP (CxTools sobre
  client fake); assercao do harness J8 (`AgentRun` sintetico - tool + slug + grounding).
- **Spike e2e (sem TDD)**: 1 chamada `python -m src.evals.run J8` (claude -p contra o /mcp).

## 7. Riscos

- Ranking lexico nao capta sinonimia: aceitavel p/ KB pequena e curada (ADR-0004); tags ajudam.
- Grounding por overlap pode ser leniente: priorizar tool-call + slug (robustos).

## 8. PR relacionado

- Branch: `feature/SPEC-005-knowledge-retrieval`. PR a preencher ao abrir.
