# SPEC-000 - Fundacao de dominio e seed

- Status: Approved (merged) — PR #1
- Versao alvo: 0.1.0 (fundacao; nao e o vertical slice)
- ADRs: ADR-0001, ADR-0004, ADR-0005

## 1. Problema

Sem um modelo de dominio e dados realistas, nao da para construir nem avaliar as jornadas de CX de energia. Precisamos da base: schema, value objects com invariantes e um seed determinístico.

## 2. Objetivo

Estabelecer o nucleo de dominio (Billing, Outage, Ticketing, Knowledge, Conversation) e um seed re-executavel que sustente as jornadas J1-J7 e os cenarios de eval.

## 3. Escopo

- Value objects com validacao (CPF, Telefone, Dinheiro, MesReferencia).
- Modelos de persistencia (SQLAlchemy, src/infrastructure/orm.py) sobre o schema SQL versionado em db/init/01-schema.sql (sem Alembic).
- Repositorios por aggregate (Billing, Outage, Ticketing, Knowledge, Conversation).
- Script de seed determinístico, idempotente, parametrizado por `.env`.

## 4. Fora de escopo

- Ferramentas MCP, agente, canal Omni, UI (vem em SPECs seguintes).
- Retrieval semantico (stretch, ADR-0004).

## 5. Criterios de aceite

- `CPF` invalido e rejeitado na construcao; `CPF` gerado pelo seed e valido no digito verificador.
- `python -m src.infrastructure.seed` popula o banco e, rodado duas vezes, nao duplica linhas (upsert por chave natural).
- Existe exatamente 1 interrupcao ativa no bairro da persona `ana.souza`.
- Cada UC tem 24 faturas (uma por mes), com sazonalidade verificavel (media verao > media inverno).
- Telefones ausentes no `.env` viram placeholders sem quebrar o seed.

## 6. Plano de testes

- Unit: value objects (CPF modulo 11, Telefone E.164, Dinheiro em centavos, MesReferencia).
- Integration: schema (db/init/01-schema.sql) + seed contra Postgres efemero; contagem por tabela; idempotencia (rodar 2x).
- Propriedade: consumo de verao > inverno por UC.

## 7. Riscos

- WeasyPrint/embedded libs em sandbox: validar cedo (afeta SPEC de PDF, nao esta).
- Divergencia entre dicionario de dados e modelos: teste de schema-vs-doc como guarda.

## 8. PR relacionado

- Branch: `feature/SPEC-000-domain-seed`.
- PR #1 (merged): https://github.com/edgardamasceno-dev/khal-ai-challenge/pull/1
  - Incremento 1 (ADR-0006, passo 1): serviço `database` (Postgres 18) + schema
    SQL + seed determinístico/idempotente via `docker compose`. Valida os
    critérios de aceite de dados (24 faturas/UC, 1 outage ativa, sazonalidade,
    idempotência).
  - Entregue: value objects (src/domain/shared/value_objects.py), modelos
    SQLAlchemy (src/infrastructure/orm.py) sobre schema SQL, repositórios e seed
    determinístico em Python.
