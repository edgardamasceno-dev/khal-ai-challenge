# ADR-0008 - Seeder programático em Python (personas dinâmicas)

- Status: Accepted
- Data: 2026-05-30
- SPEC: SPEC-006

## Context

O seed era um `db/seed.sql` estático aplicado no init do Postgres (`db/init/02-seed.sh`,
via `psql -v` com telefones do `.env`), com **3 personas hardcoded** (Ana, Carlos, Joana).
A SPEC-006 pede personas **dirigidas por `.env`** (`SEED_PERSONAS`, de 1 a ~100), cada uma
com um **perfil determinístico** (bairro, consumo, faturas, outage, multi-UC), e que **seed
e evals derivem da mesma fonte**.

Gerar N personas com CPF de DV válido, 24 meses de leituras/faturas com sazonalidade,
status por cenário e idempotência por chave natural — tudo parametrizado — é inviável e
insalubre em SQL estático interpolado por shell. Além disso, a lógica de perfil precisa ser
**compartilhada** com o harness de evals (Python).

## Decision

O seed passa a ser um **seeder programático em Python** (`python -m src.infrastructure.seed`,
ADR-0001), que conecta via **SQLAlchemy 2.0** e faz **upsert idempotente**
(`INSERT ... ON CONFLICT DO NOTHING`, IDs determinísticos por `uuid5`). A fonte de personas
é o domínio `src/domain/persona` (`perfil_de(telefone, seed)` — função pura) exposto pelo
`persona_registry` (application), **consumido por seed e evals** (DRY).

No `docker-compose`, o seed vira um **serviço one-shot** (`seed`, imagem do backend,
`restart: "no"`) que roda após `database` saudável; o `backend` depende dele com
`service_completed_successfully`. O Postgres só recebe o **schema** no init (`01-schema.sql`).

## Consequences

Positivas:
- Personas dinâmicas (1..N) por `.env`, sem tocar em código; perfis determinísticos e ricos.
- Lógica de perfil única, reaproveitada pelos evals (sem divergência seed↔eval).
- Idempotência e determinismo testáveis em pytest (unit + integration), no mesmo runner.
- Alinhado à stack (Python/SQLAlchemy/Repository) em vez de SQL+shell.

Negativas:
- O seed agora exige a imagem da aplicação (não roda mais "puro" no init do Postgres).
  Mitigado: serviço one-shot no compose; entrypoint único `python -m src.infrastructure.seed`.
- Timestamps de dados "ativos agora" (outage, chamado) usam `now()` real (não determinístico),
  como antes; a idempotência usa chave natural (bairro+causa / idempotency_key), não o tempo.

## Alternatives

- **Gerar o SQL dinamicamente em shell/Python e aplicar via psql no init**: rejeitada —
  duas linguagens, geração de SQL frágil, sem reuso pelos evals, difícil de testar.
- **Manter SQL estático e só parametrizar telefones**: rejeitada — não atende N personas
  nem perfis variados; mantém a duplicação seed↔eval.
