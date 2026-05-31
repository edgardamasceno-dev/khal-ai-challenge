# ADR-0011 - Personas canônicas com cenário fixo por nome (overlay determinístico)

- Status: Accepted
- Data: 2026-05-31
- SPEC: SPEC-006

## Context

A SPEC-006 deriva **todo** o `PerfilPersona` por hash do telefone
(`perfil_de(telefone, seed)`): classe, bairro, `n_ucs`, `cenario_fatura`,
`outage_ativa`, `corte_religacao`. O default do `.env.example` são as **3 personas
canônicas** (Ana/Carlos/Joana), e o desafio espera ver delas cenários específicos:

- **Ana Souza** — residencial, bairro "Jardim das Flores", **fatura vencida + outage ativa**;
- **Carlos Lima** — **comercial, multi-UC**, em dia;
- **Joana Pereira** — **rural, com corte + religação**.

Com `SEED_RANDOM_SEED=42` e os telefones default, a derivação por hash **não** reproduz
esses cenários (Ana caía em "Centro", sem outage; Carlos vinha residencial; Joana sem
corte). Pior: o modo **rico** (`rico=True`) só dispara com `len(personas)==1`, então o
default (3 personas) **não** recebia cenário rico. O efeito vazava:

- o **seeder** só materializa interrupção/religação se `perfil.outage_ativa` /
  `perfil.corte_religacao` — logo o banco de demo não tinha a outage da Ana nem o corte da Joana;
- o **builder de evals** só emite a jornada J2 (falta de energia) `if perfil.outage_ativa` —
  então, com o default, **a J2 era silenciosamente removida da suíte**.

A demo e os evals ficavam **infiéis** aos cenários canônicos e dependiam de "sorte" na
derivação.

## Decision

Fixar os cenários das **3 personas canônicas por NOME** (`persona_key` = slug do nome,
mesma normalização do seeder), via um **overlay determinístico** em `perfil_de`, com a
precedência:

```
canônico-por-nome  >  rico (persona única)  >  derivado
```

- O overlay (`_CANONICOS`, indexado por `persona_key`) fixa **apenas os campos de cenário**:
  `classe`, bairro (Ana → "Jardim das Flores"), `subgrupo`/consumo coerentes com a classe,
  `cenario_fatura`, `outage_ativa`, `corte_religacao` e — para Carlos — um **mínimo de UCs**
  (`n_ucs ≥ 2`). É aplicado **independente do telefone**: Ana é canônica com qualquer número.
- **Campos derivados do telefone permanecem derivados** (CPF, consumo das UCs): o overlay não
  troca o algoritmo de hash. A **ordem dos draws** do RNG do caminho derivado foi preservada
  byte-a-byte, então **qualquer telefone fora do conjunto canônico continua com o mesmo
  perfil de antes** (regressão travada por teste sobre 500+ telefones).
- `perfil_de` ganha o argumento opcional `nome`/`persona_key`; o `persona_registry` repassa o
  `nome` da persona. Sem `nome`/`persona_key`, o comportamento é o baseline (puramente derivado).

## Consequences

Positivas:
- Demo e evals **fiéis e reproduzíveis** aos cenários que a banca espera (Ana com
  outage+fatura vencida, Carlos comercial multi-UC, Joana rural com corte) — sem depender de sorte.
- A jornada **J2 (outage) volta a ser gerada** para Ana no default; o seeder materializa a
  interrupção ativa no bairro dela e o chamado de religação da Joana, de forma idempotente.
- **Determinismo preservado**: nada usa `hash()` do Python nem `random` global; CPF com DV
  válido e estável por telefone; `uuid5` no seeder inalterado.

Negativas / limites:
- A fixação é **cirúrgica** (só os 3 `persona_key`). Personas adicionais seguem 100% derivadas
  — é uma escolha consciente para não quebrar o determinismo das personas dinâmicas (SPEC-006).
  Mitigado por testes que travam os **dois** lados (canônico exato + baseline preservado).
- Acopla os nomes canônicos ("Ana Souza"/"Carlos Lima"/"Joana Pereira") ao slug. Trocar o
  nome no `.env` desliga o overlay (a persona vira derivada) — comportamento desejado e documentado.

## Alternatives

- **Mudar o algoritmo de hash/derivação para os telefones canônicos caírem nos cenários
  certos**: rejeitada — quebraria o determinismo de todas as outras personas e seria frágil
  (qualquer mudança de pesos/locais reabriria o problema).
- **Forçar `rico=True` no default**: rejeitada — `rico` é um cenário único (residencial +
  outage), não distingue Carlos (comercial) de Joana (rural).
- **Hardcodar os perfis canônicos numa tabela de seed estática**: rejeitada — contraria a
  ADR-0008 (seeder programático) e a fonte única do registry; reintroduz divergência seed↔eval.
