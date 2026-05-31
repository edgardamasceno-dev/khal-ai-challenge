# SPEC-013 - 1 a 4 unidades consumidoras por persona (seed)

- Status: Approved (2026-05-30)
- Versao alvo: 1.2.2 (perfil deriva 1..4 UCs por persona)
- ADRs: ADR-0008 (personas dinâmicas / derivação determinística). Sem ADR novo.

## 1. Problema

Hoje a derivação (`perfil_de`) dá **1 UC** por persona — só `comercial` chega a 2
(`n_ucs = 2 if comercial and rng.random() < 0.6 else 1`). O cenário multi-UC quase
não aparece, e o operador/evals não exercitam clientes com várias unidades.

## 2. Objetivo

Cada persona passa a ter **1 a 4 UCs**, determinístico (mesmo telefone+seed -> mesmo
número). Distribuição ponderada por classe (comercial tende a mais unidades).

### Decisão de design (preservar determinismo dos evals)
Mudar `n_ucs` inline deslocaria a sequência do RNG principal e alteraria
`cenario_fatura`/`outage_ativa`/`corte_religacao` de todas as personas. Para evitar:
- `n_ucs` e os consumos das **UCs extras** vêm de um **RNG dedicado**
  (`_rng(telefone + ":ucs", seed)`), stream independente.
- O RNG principal mantém: cpf -> classe -> bairro -> **base_kwh da UC primária** ->
  cenario -> outage -> corte. Some o draw `rng.random()<0.6` (só afetava comerciais).
- Resultado: **residenciais e rurais ficam idênticas** (cenário/outage/corte intactos);
  só comerciais mudam de sequência — e nenhuma persona canônica é comercial.

## 3. Escopo

- `derivation.py`: `n_ucs = rng_ucs.choices((1,2,3,4), weights=_UC_WEIGHTS[classe])`;
  `base_kwh = (base_uc0_principal, *extras_do_rng_ucs)`.
- `models.py`: comentário `n_ucs # 1..4`; invariante `1 <= n_ucs <= 4`.
- Seeder **inalterado**: já itera `range(n_ucs)` por idx, gera `numero_uc` único por idx,
  e só a UC primária (idx 0) carrega o cenário de fatura (extras = faturas normais).

## 4. Fora de escopo

- Cenários de fatura/outage por UC extra (continua só na primária).
- Tornar os pesos configuráveis por env.

## 5. Plano TDD

1. **Derivação** (unit): `n_ucs ∈ 1..4`; `len(base_kwh) == n_ucs`; determinístico;
   numa amostra de telefones a distribuição cobre os 4 valores.
2. **Regressão de sequência** (unit): residenciais/rurais preservam
   `cenario_fatura`/`outage_ativa`/`corte_religacao` (telefones canônicos).
3. **Seeder** (integration): persona com n_ucs>1 gera várias UCs com `numero_uc` distinto.
4. **Regressão**: suite verde; evals não quebram (build_scenarios dinâmico).

## 6. Critérios de aceite

- `perfil_de` devolve 1..4 UCs, determinístico; consumo por UC coerente.
- Cenários canônicos (vencida/outage/corte) preservados nas personas existentes.
- unit+integration+lint/typecheck verdes.
