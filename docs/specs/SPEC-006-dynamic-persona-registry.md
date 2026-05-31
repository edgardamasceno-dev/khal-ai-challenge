# SPEC-006 - Registry de personas dinâmico (seed + evals)

- Status: Approved (2026-05-30) — PR #8
- Versao alvo: 0.7.0 (personas dirigidas por `.env`, seed e evals derivados)
- Decisao de perfil (1 persona): quando `len(personas)==1`, garantir perfil **rico**
  (>=1 fatura vencida + outage no bairro) para exercitar as tools na demo.
- Decisao de perfil (3 canônicas / **ADR-0011**): os cenários das personas default
  (Ana/Carlos/Joana) são **fixos por nome** (`persona_key`), independentes do telefone —
  **canônico-por-nome > rico > derivado**. Garante demo/evals fiéis (Ana com outage+fatura
  vencida, Carlos comercial multi-UC, Joana rural com corte). Personas adicionais seguem 100%
  derivadas; telefones não-canônicos mantêm o perfil de antes (baseline preservado).
- ADRs: **ADR-0008 (novo)** - seeder programático em Python (substitui o seed SQL-on-init);
  **ADR-0011 (novo)** - overlay canônico determinístico por nome.
  Mantém ADR-0001 (Python), ADR-0007 (runtime do agente). Não contraria os demais.

## 1. Problema

Hoje o seed tem **3 personas fixas** (Ana, Carlos, Joana) hardcoded em `db/seed.sql`,
com telefones injetados via `psql -v` (`db/init/02-seed.sh`). Os evals (`src/evals/journeys.py`)
repetem esses telefones em constantes (`ANA`, `CARLOS`). Consequências:

1. Para demonstrar com um **número real de WhatsApp** (ex.: o do operador), é preciso
   editar `.env` **e** torcer para o telefone cair numa persona com cenário útil.
2. Não há como ter **N personas** (1..~100) sem editar SQL e Python à mão.
3. Seed e evals **duplicam** a noção de "quem é cliente e qual o cenário" — fácil divergir.

## 2. Objetivo

Uma **fonte única de personas** no `.env`, consumida por **seed e evals**, onde cada
persona ganha um **perfil determinístico** (derivado do telefone + `SEED_RANDOM_SEED`) que
**simula um cliente real** (bairro, consumo, faturas, outage/corte, multi-UC). Adicionar
uma persona ao `.env` passa a gerar, sozinho, **dados realistas no banco + casos de eval**
para ela — sem tocar em código.

### Decisão de arquitetura (pinada aqui)

- **`persona_registry` (módulo Python, fonte única)**: lê `SEED_PERSONAS` do ambiente,
  produz `Persona(nome, telefone)` e deriva `PerfilPersona` **determinístico** por persona.
  Importado tanto pelo **seeder** quanto pelo **harness de evals** (DRY, sem divergência).
- **Seeder programático (ADR-0008)**: o seed deixa de ser `db/seed.sql` aplicado no init do
  Postgres e passa a ser um **comando Python** (`python -m src.infrastructure.seed`) que
  conecta via SQLAlchemy e faz **upsert** idempotente. Motivo: a geração por-persona
  (N variável, perfis, CPF com DV válido, 24m de histórico) é inviável/insalubre em SQL
  estático; Python alinha com a stack (ADR-0001) e com o Repository pattern.
- **Evals derivados**: as `Scenario`s persona-dependentes (fatura, outage, multi-UC,
  cross-access) são **geradas a partir do registry + perfil**; as comportamentais
  (injection, cliente desconhecido, fora de escopo, KB, handoff) permanecem **fixas**.

## 3. Escopo

- **`SEED_PERSONAS`** (env): `"Nome:telefone;Nome:telefone;..."` (telefone E.164 sem `+`),
  **≥1**, suportando ~100. Parser tolerante (trim, ignora entradas vazias, valida telefone).
- **`src/domain/persona/`** (domínio puro): `Persona`, `PerfilPersona` (value objects) e a
  **derivação determinística** `perfil_de(telefone, seed) -> PerfilPersona`:
  - `bairro`, `cidade`, `uf`, `classe`, `subgrupo`;
  - `n_ucs` ∈ {1,2,3,4} (ampliado de {1,2} pela SPEC-013); `base_kwh` (tupla) por UC;
  - **cenário de fatura** ∈ {em_dia, uma_aberta, uma_vencida};
  - `outage_ativa` (bool) no bairro; `corte_religacao` (bool);
  - CPF fictício com **dígito verificador válido**, derivado do telefone (estável/idempotente);
  - tudo função pura de `(telefone, seed)` → reproduzível.
- **`persona_registry`** (application): `carregar_personas(env) -> list[(Persona, PerfilPersona)]`.
- **Seeder** `src/infrastructure/seed/`: gera, por persona/perfil, `titulares`, `unidades_consumidoras`,
  `contratos`, `leituras` (24m, sazonalidade), `faturas` (status conforme o cenário),
  `interrupcoes`, `chamados`. Idempotente por chave natural (CPF, numero_uc, mes_referencia,
  protocolo, idempotency_key). Determinístico (`SEED_RANDOM_SEED`).
- **Orquestração**: serviço/etapa one-shot no `docker-compose` que roda o seeder após o
  `database` saudável (substitui `db/init/02-seed.sh`).
- **Evals**: `persona_registry` alimenta `journeys.py`. Para cada persona com perfil
  relevante, gera os casos (fatura/outage/multi-UC). Cross-access usa **outra** persona do
  registry se houver ≥2, senão um telefone fabricado **fora** do registry (cliente alheio).
- **Docs**: `seed-design.md`, `CLAUDE.md` (seção Personas), `.env.example` (default = as 3
  canônicas como `SEED_PERSONAS`), README de execução.

## 4. Fora de escopo

- LLM-as-judge / Agent Score (segue determinístico, como SPEC-004/005).
- Geração de PII real ou nomes de pessoas reais no repositório (apenas placeholders no
  `.env.example`; números reais **só** no `.env` local, gitignored).
- Mudança de schema do legado (SPEC-001). O seeder popula as tabelas existentes.
- Internacionalização de telefones fora do padrão BR (E.164 genérico é aceito, mas o perfil
  assume DDD/BR para bairro/cidade fictícios).

## 5. Domínio e contratos

### `PerfilPersona` (determinístico, derivado de `(telefone, seed)`)

| Campo            | Tipo            | Observação                                            |
|------------------|-----------------|-------------------------------------------------------|
| `cpf`            | str (11)        | DV válido (mod 11), fictício, estável por telefone     |
| `bairro`/`cidade`| str             | de uma lista fictícia, escolhido por hash              |
| `classe`/`subgrupo`| enum          | residencial/comercial/rural                            |
| `n_ucs`          | 1..4            | distribuicao ponderada por classe (comercial tende a mais UCs); SPEC-013 |
| `base_kwh`       | tuple[int] (um por UC) | consumo base; leituras com sazonalidade verão +35%     |
| `cenario_fatura` | enum            | `em_dia` \| `uma_aberta` \| `uma_vencida`              |
| `outage_ativa`   | bool            | interrupção não programada ativa no bairro             |
| `corte_religacao`| bool            | histórico de corte + religação                         |

Garantia: **mesma entrada → mesma saída** (sem `random` global; usa hash estável do
telefone combinado a `SEED_RANDOM_SEED`).

### `SEED_PERSONAS` (env)

```
SEED_PERSONAS="Ana Souza:555199990001;Carlos Lima:555199990002;Joana Pereira:555199990003"
```

- `.env.example`: as **3 canônicas** (placeholders) — evals com cenários conhecidos out-of-box.
- `.env` local do operador: o que quiser (ex.: só o número real dele), ≥1, até ~100.
- Telefone inválido/duplicado → erro claro no seeder (falha cedo).

## 6. Migração / compatibilidade

- Remove `db/seed.sql` + `db/init/02-seed.sh` (vira ADR-0008). Mantém um caminho de
  re-seed do zero (`compose down -v` + up roda o seeder).
- Remove `DEMO_PHONE_*`/`DEMO_DEFAULT_PERSONA`; `UNKNOWN_PHONE_BEHAVIOR` permanece.
- `journeys.py`: constantes `ANA`/`CARLOS` saem; telefones vêm do registry. As 3 canônicas
  continuam sendo o default, então as jornadas J1..J8 seguem cobertas por padrão.
- Atualiza o sandbox (`poc/sandbox`): o agente CX e o E2E usam um telefone do registry.

## 7. Plano TDD (red → green → refactor)

1. **Domínio** `perfil_de`: testes de determinismo (mesma entrada→saída), DV de CPF válido,
   distribuição de cenários, estabilidade entre execuções. (red→green)
2. **Parser** `SEED_PERSONAS`: 1 persona, N personas, espaços, entradas inválidas. (red→green)
3. **Seeder**: contra Postgres efêmero (mesmo runner Docker dos outros testes) — idempotência
   (rodar 2x não duplica), contagem por persona, faturas conforme cenário, outage no bairro. (red→green)
4. **Evals**: harness gera os casos a partir do registry; um perfil com outage gera o caso
   de outage e ele passa; cross-access usa 2ª persona/telefone alheio. (red→green)
5. **Regressão**: suíte de evals ≥ 85/100 com o default (3 canônicas). **Bloqueia o PR** se cair.
6. **Docs/ADR**: ADR-0008, `seed-design.md`, `CLAUDE.md`, `.env.example`, READMEs.

## 8. Riscos e mitigação

- **Cobertura com 1 persona**: perfil único pode não exercer todas as tools. Mitigação: o
  perfil é **rico** (≥1 fatura, leituras, e ao menos um entre outage/corte garantido quando
  `len(personas)==1`), e os casos comportamentais independem de persona.
- **Determinismo quebrado por `dict`/hash não estável**: usar hash explícito (`hashlib`) do
  telefone, nunca `hash()` do Python (seed por processo).
- **Seeder fora do init do Postgres**: precisa do `database` saudável antes; orquestrar via
  `depends_on: condition: service_healthy` + serviço one-shot.

## 9. Critérios de aceite

- `SEED_PERSONAS` com **1** persona (só o operador) → banco populado e demo funcional; com
  **N** (até ~100) → idem, sem editar código.
- Seed **idempotente** e **determinístico** (re-run não duplica; mesma `SEED_PERSONAS`+seed
  → mesmos dados).
- Evals **derivam** do registry; suíte ≥ 85/100 com o default; regressão bloqueia PR.
- Nenhum número real versionado (só `.env`); `.env.example` com placeholders.
- `unit + integration + e2e + lint/typecheck` verdes no HEAD do PR.
```
