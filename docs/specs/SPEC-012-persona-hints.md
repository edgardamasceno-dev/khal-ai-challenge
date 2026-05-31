# SPEC-012 - Primeira tela reflete personas reais cadastradas

- Status: Approved (2026-05-30)
- Versao alvo: 1.2.1 (login do console lista personas do banco)
- ADRs: ADR-0008 (personas dinâmicas via SEED_PERSONAS). Sem ADR novo.

## 1. Problema

A primeira tela (`App.tsx`) traz telefone default, placeholder e dicas de persona
**hardcoded** (`555199990001 (Ana)`, `…002 (Carlos)`, `…003 (Joana)`). Com personas
dinâmicas (`SEED_PERSONAS`, SPEC-006/ADR-0008) isso **não reflete** quem está cadastrado —
o operador não sabe quais telefones existem de fato.

## 2. Objetivo

A tela lista as **personas realmente cadastradas** (nome + telefone), vindas do banco,
como atalhos clicáveis que preenchem o campo de busca. Sem números fixos no código.

### Decisões
- Fonte de verdade = tabela `titulares` (já seedada). Sem ler `SEED_PERSONAS` no backend.
- O telefone vem **em claro** (atalho de busca do console interno do operador; nada é
  versionado). É o mesmo número que o operador digitaria.

## 3. Escopo

### Back
- `TitularRepository.list_all()` -> todos os titulares.
- `BillingService.list_personas()` -> lista de titulares (ordenada por nome).
- `PersonaHintDTO {nome, telefone, persona_key}`; REST `GET /personas` -> `list[PersonaHintDTO]`.

### Front (console)
- `App.tsx` busca `/personas` no mount e renderiza **chips clicáveis** (nome + telefone)
  que preenchem o input. Remove os 3 hardcodes (default, placeholder, dicas). Sem telefone
  default fixo; fallback neutro se a lista vier vazia.

## 4. Fora de escopo

- Paginação/busca incremental de personas (lista é pequena: 1..~100).
- Mascarar o telefone nos chips (é o atalho de busca; precisa do número em claro).

## 5. Plano TDD

1. **Repo** (integration): `list_all` devolve os titulares seedados.
2. **Service** (unit, fakes): `list_personas` ordena por nome.
3. **REST** (api): `GET /personas` devolve nome/telefone/persona_key.
4. **Front**: chips clicáveis + sem hardcode (build do console).
5. **Regressão**: suite verde.

## 6. Critérios de aceite

- `GET /personas` devolve as personas cadastradas (nome, telefone em claro, persona_key).
- A tela mostra atalhos clicáveis reais; nenhum telefone/nome fixo no código.
- unit+integration+api+lint/typecheck verdes; console builda.
