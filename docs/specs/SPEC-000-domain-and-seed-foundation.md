# SPEC-000 - Fundacao de dominio e seed

- Status: Draft
- Versao alvo: 0.1.0 (fundacao; nao e o vertical slice)
- ADRs: ADR-0001, ADR-0004, ADR-0005

## 1. Problema

Sem um modelo de dominio e dados realistas, nao da para construir nem avaliar as jornadas de CX de energia. Precisamos da base: schema, value objects com invariantes e um seed determinístico.

## 2. Objetivo

Estabelecer o nucleo de dominio (Billing, Outage, Ticketing, Knowledge, Conversation) e um seed re-executavel que sustente as jornadas J1-J7 e os cenarios de eval.

## 3. Escopo

- Value objects com validacao (CPF, Telefone, Dinheiro, MesReferencia).
- Modelos de persistencia (SQLAlchemy) + migracoes Alembic das tabelas do dicionario de dados.
- Repositorios por aggregate (Billing, Outage, Ticketing, Knowledge, Conversation).
- Script de seed determinístico, idempotente, parametrizado por `.env`.

## 4. Fora de escopo

- Ferramentas MCP, agente, canal Omni, UI (vem em SPECs seguintes).
- Retrieval semantico (stretch, ADR-0004).

## 5. Criterios de aceite

- `CPF` invalido e rejeitado na construcao; `CPF` gerado pelo seed e valido no digito verificador.
- `make seed` popula o banco e, rodado duas vezes, nao duplica linhas (upsert por chave natural).
- Existe exatamente 1 interrupcao ativa no bairro da persona `ana.souza`.
- Cada UC tem 24 faturas (uma por mes), com sazonalidade verificavel (media verao > media inverno).
- Telefones ausentes no `.env` viram placeholders sem quebrar o seed.

## 6. Plano de testes

- Unit: value objects (CPF modulo 11, Telefone E.164, Dinheiro em centavos, MesReferencia).
- Integration: migracoes + seed contra Postgres efemero; contagem por tabela; idempotencia (rodar 2x).
- Propriedade: consumo de verao > inverno por UC.

## 7. Riscos

- WeasyPrint/embedded libs em sandbox: validar cedo (afeta SPEC de PDF, nao esta).
- Divergencia entre dicionario de dados e modelos: teste de schema-vs-doc como guarda.

## 8. PR relacionado

- A preencher ao abrir o PR (`feature/SPEC-000-domain-seed`).
