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

- Default (`.env.example`): as 3 canônicas (Ana/Carlos/Joana) — evals com cenários conhecidos.
- Cada persona é derivada por `perfil_de(telefone, seed)` (função pura, `src/domain/persona`):
  bairro/cidade/classe, `n_ucs` (1..2), consumo base, **cenário de fatura**
  (`em_dia`/`uma_aberta`/`uma_vencida`), `outage_ativa` no bairro, `corte_religacao`.
- **Persona única** (ex.: só o número real do operador): recebe **perfil rico** (fatura
  vencida + outage ativa) para exercitar as tools na demo.
- Números reais de demo vivem **só no `.env`** local (gitignored), nunca no repositório.

## CPF ficticio valido

Geramos 9 digitos base a partir do RNG e calculamos os 2 digitos verificadores pelo algoritmo oficial (modulo 11). Resultado: passa em validacao de formato/digito, mas e ficticio e rotulado como teste. Nunca usar CPF de pessoa real.

## Conteudo gerado por persona

- **Titular** + contatos + `persona_key`.
- **UC(s)**: Ana 1, Carlos 2, Joana 1. Bairro de Ana = "Jardim das Flores".
- **Leituras + Faturas**: uma por mes de referencia (24 meses), com:
  - **sazonalidade**: consumo maior no verao (dez-mar) por ar-condicionado;
  - **bandeira** correlacionada (vermelha em meses secos/quentes);
  - **status**: meses antigos `paga`, mes atual de Ana `em_aberto`, um mes `vencida`;
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
make seed     # python -m scripts.seed (le .env)
```

Saida esperada: resumo por tabela (linhas inseridas/atualizadas) e os telefones efetivamente mapeados (mascarados em log).

## Relacao com evals

Os evals usam telefones controlados: um conhecido (persona do seed) e um deliberadamente **fora do seed** para o caso "cliente desconhecido". O fallback de persona default e comportamento de **demo**, nao de eval (`UNKNOWN_PHONE_BEHAVIOR`).
