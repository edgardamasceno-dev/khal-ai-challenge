# ADR-0017 - Camada legada (FastAPI + Postgres) como sistema integrado via MCP-over-REST (Anti-Corruption Layer)

- Status: Accepted
- Data: 2026-05-31
- Item do roadmap: M-04 (`docs/11-roadmap-melhorias-agente.md`).
- Relaciona-se com: ADR-0001 (stack Python/hexagonal-DDD), ADR-0003/0010 (PDF/midia como acao de
  tool, nao pelo reply), ADR-0006 (sandbox so-MCP — a rede que **forca** o agente a passar pela
  ACL), ADR-0012 (auditoria por tool-call — observabilidade da fronteira), ADR-0013 (fronteira de
  memoria). Da nome arquitetural a uma propriedade que ja existe no codigo; **nao** muda
  implementacao.

## Context

A vaga Senior/Lead cita "integrar sistemas legados (APIs/CRMs/ERPs/telefonia)" como
responsabilidade. No artefato, o **"sistema legado" e simulado** pela camada **FastAPI + Postgres
+ console React** (dona dos dados e das acoes de negocio: clientes, contratos, faturas, outages,
tickets, memoria). O **agente nunca fala com essa camada diretamente**: ele so alcanca o negocio
pelo **mcp-server**, que traduz **tools tipadas (Pydantic) → chamadas REST** (`LegacyApiClient` /
`HttpxLegacyApiClient` em `src/interfaces/mcp/`). A topologia de rede (ADR-0006) **garante** isso:
a sandbox so enxerga `mcp-server`; `backend`/`database` sao inalcancaveis (validado: → 000).

Essa propriedade — agente isolado do legado, falando so por um tradutor com guardrails — e
exatamente um **Anti-Corruption Layer (ACL)** do DDD, mas nunca foi **nomeada** como decisao. O
gap nao e de codigo (ja esta la), e de **narrativa arquitetural**: registrar *por que* o
mcp-server e o ACL e *quais propriedades* isso garante.

## Decision

Declarar o **mcp-server como Anti-Corruption Layer** entre o agente (modelo conversacional,
nao-confiavel quanto a entrada) e o **sistema legado** (FastAPI + Postgres). O padrao de
integracao e **MCP-over-REST**: cada tool MCP e um caso de uso traduzido em uma (ou poucas)
chamada(s) REST tipada(s) ao legado, **nunca** acesso direto ao banco nem ao dominio do legado.

Propriedades que o ACL garante (e que esta ADR formaliza):

1. **Tradutor de modelos (Adapter).** A tool expoe um contrato **estavel e amigavel ao agente**
   (Pydantic in/out, nomes do dominio em pt-BR) e **isola** o agente do shape REST/SQL do legado.
   Mudar o legado nao quebra o contrato do agente enquanto a tool traduzir — e a razao de ser do
   ACL.
2. **Fronteira de guardrail deterministico.** Acesso **so ao titular** resolvido pelo telefone do
   remetente (nao contornavel por injection); confirmacao + idempotencia antes de escrita
   (`create_ticket`); validacao Pydantic em toda tool. O agente **nao tem** outro caminho ao
   negocio (rede so-MCP, ADR-0006) — o ACL e a **unica** porta, e ela e fechada por codigo, nao
   por prompt.
3. **Ponto unico de observabilidade.** Todo cruzamento da fronteira passa pelo funil de
   `AuditedCxTools` (ADR-0012): latencia, status (`ok/denied/error`), PII mascarada, e o `trace_id`
   propagado (R-10) — um lugar so para auditar a integracao agente↔legado.
4. **Degradacao graciosa (M-03).** Quando o legado cai, o ACL **converte** o erro de transporte
   num **erro tipado amigavel** (shape estavel `{"erro": ...}`), **nao** repassa stacktrace cru —
   o agente nao alucina sobre dados que nao conseguiu ler. A traducao de falha tambem e
   responsabilidade do ACL.

Direcao da dependencia: o **mcp-server depende do legado** (consome o REST), nunca o contrario; o
legado nao conhece o agente. Isso preserva o legado como **sistema integrado**, nao como modulo
acoplado ao agente.

## Consequences

Positivas:
- Da **nome e justificativa** a uma propriedade ja entregue: "integrar sistema legado" vira uma
  **decisao arquitetural legivel** (ACL via MCP-over-REST), nao um detalhe de implementacao.
- O contrato do agente fica **desacoplado** da evolucao do legado: trocar o backend (outro
  ERP/CRM real) e re-pontar os adapters do `LegacyApiClient`, sem tocar tools/AGENTS.md/evals.
- Reforca os guardrails: a unica porta ao negocio e auditada, tipada e fechada por codigo.

Negativas / trade-offs:
- Toda capacidade nova do negocio exige **uma tool + traducao REST** (nao "o agente consulta o
  banco") — e o custo intencional do isolamento; aceitavel e desejavel.
- Latencia extra do hop REST por tool-call; mitigada por ser local e pelo caching/CAG (ADR-0014)
  que reduz idas ao MCP.

## Alternatives

- **Agente acessando o banco/dominio do legado direto** (sem ACL): rejeitado — quebraria o
  guardrail de acesso-so-ao-titular, exporia o agente a injection contra dados, e acoplaria o
  contrato do agente ao schema do legado.
- **ACL como modulo no proprio backend** (em vez de servico MCP separado): rejeitado — perderia o
  isolamento de rede (ADR-0006) que torna o guardrail nao-contornavel, e o ponto unico de auditoria
  MCP (ADR-0012).
- **Nao nomear (deixar implicito no codigo):** rejeitado — a responsabilidade "integrar legado" e
  nominal na vaga; sem a ADR, o sinal arquitetural fica invisivel ao avaliador.
