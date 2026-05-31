# Design do seed

Objetivo: massa ficticia mas realista, **determinística** e re-executavel, que sustente todas as jornadas (`personas-journeys.md`) e os cenarios de eval.

> **Atualizado pela SPEC-006 / ADR-0008.** O seed é **programático** (Python/SQLAlchemy,
> `python -m src.infrastructure.seed`), não mais SQL estático. Personas vêm de `SEED_PERSONAS`
> e cada uma ganha um **perfil determinístico** — a mesma derivação alimenta o seed e os evals.

## Principios

- Determinismo: `SEED_RANDOM_SEED` (default 42) fixa a derivação. Mesma entrada, mesmo banco.
- Re-executavel (idempotente): rodar o seed de novo nao duplica; upsert por chave natural
  (CPF, numero_uc, (uc_id, mes_referencia), protocolo, idempotency_key) + IDs `uuid5`.
- Sem PII real: CPFs com digito verificador valido porem ficticios; nomes/telefones via `.env`.
- Horizonte: `SEED_HISTORY_MONTHS` (default 24).

## Personas dinâmicas (`SEED_PERSONAS`)

Fonte única, lida do `.env`, consumida por **seed e evals**:

```text
SEED_PERSONAS="Nome:telefone;Nome:telefone;..."   # E.164 sem '+', >=1, ate ~100
```

- Default (`.env.example`): as 3 canônicas (Ana/Carlos/Joana) — evals com cenários **fixos**.
- Cada persona ganha um `PerfilPersona` determinístico (`src/domain/persona`):
  bairro/cidade/classe, `n_ucs` (1..4), consumo base, **cenário de fatura**
  (`em_dia`/`uma_aberta`/`uma_vencida`), `outage_ativa` no bairro, `corte_religacao`.
- **Precedência do perfil (ADR-0011): canônico-por-nome > rico > derivado.**
  - **Canônico-por-nome** (as 3 default, por `persona_key`): cenário **fixo**, independente do
    telefone — **Ana** (residencial, Jardim das Flores, fatura vencida, **outage ativa**),
    **Carlos** (comercial, **multi-UC** `n_ucs≥2`, em dia), **Joana** (rural, **corte+religação**).
    O CPF e o consumo continuam derivados do telefone (estáveis/idempotentes); só os campos de
    *cenário* são fixados. A demo e os evals (incl. J2 de outage) são fiéis a esses cenários.
  - **Rico** (`rico=True`, persona única **não-canônica**): fatura vencida + outage ativa,
    para exercitar as tools na demo.
  - **Derivado** (qualquer outra persona): tudo sorteado por `perfil_de(telefone, seed)`
    (função pura) — bairro/classe/cenário dependem do telefone+seed.
- Números reais de demo vivem **só no `.env`** local (gitignored), nunca no repositório.

## CPF ficticio valido

Geramos 9 digitos base a partir do RNG e calculamos os 2 digitos verificadores pelo algoritmo oficial (modulo 11). Resultado: passa em validacao de formato/digito, mas e ficticio e rotulado como teste. Nunca usar CPF de pessoa real.

## Conteudo gerado por persona

- **Titular** + contatos + `persona_key`.
- **UC(s)**: quantidade (1..4) e bairro são **derivados** por `perfil_de` para personas adicionais; para as 3 canônicas são **fixos** (ADR-0011) — Ana em **"Jardim das Flores"** (cenário de outage canônico, `_LOCAIS[0]`), Carlos comercial multi-UC (`n_ucs≥2`), Joana rural. O modo **persona única não-canônica** (`rico=True`) também usa "Jardim das Flores" + outage.
- **Leituras + Faturas**: uma por mes de referencia (24 meses), com:
  - **sazonalidade**: consumo maior no verao (dez-mar) por ar-condicionado;
  - **bandeira** correlacionada (vermelha em meses secos/quentes);
  - **status**: derivado do `cenario_fatura` da persona, na UC primária (`_status_fatura`): `em_dia` → todas `paga`; `uma_aberta` → mes-ancora `em_aberto`; `uma_vencida` → mes-ancora `em_aberto` e o mes anterior `vencida`; demais meses `paga`;
  - `linha_digitavel` e `pix_copia_cola` ficticios.
- **Pagamentos**: um por fatura paga, com `idempotency_key`.
- **Interrupcoes**: 1 **ativa** no bairro de Ana (nao_programada, com previsao de retorno) + 1-2 historicas encerradas.
- **Chamados**: 1-2 resolvidos no historico + 1 aberto (para J4); SLA por tipo.
- **Religacao**: Joana com fatura que gerou corte e posterior religacao.

## Volume aproximado

~3 titulares, ~4 UCs, ~96 faturas (4 UCs x 24m), ~80 pagamentos, ~3 interrupcoes, ~5 chamados. Suficiente para demo e evals sem inflar o banco.

## Execucao

```bash
make db-up
python -m src.infrastructure.seed   # le .env (SEED_PERSONAS, SEED_RANDOM_SEED, ...)
```

Saida esperada: resumo por tabela (linhas inseridas/atualizadas) e os telefones efetivamente mapeados (mascarados em log).

## Relacao com evals

Os evals usam telefones controlados: um conhecido (persona do seed) e um deliberadamente **fora do seed** para o caso "cliente desconhecido". O fallback de persona default e comportamento de **demo**, nao de eval (`UNKNOWN_PHONE_BEHAVIOR`).
