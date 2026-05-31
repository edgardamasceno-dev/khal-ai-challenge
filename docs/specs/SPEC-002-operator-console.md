# SPEC-002 - Console do operador (UI React/Shadcn)

- Status: Approved (merged) — PR #3
- Versao alvo: 0.3.0 (UI fina do legado)
- ADRs: ADR-0002 (UI como console fino), ADR-0006 (compose, frontend no gateway)
- Validado antes em POC (`poc/frontend`).

## 1. Problema

O sistema legado expoe dados e acoes (SPEC-001), mas nao ha uma interface para o
operador visualizar clientes/faturas/interrupcoes e exercitar as acoes ao vivo na
frente do avaliador. A UI nao e o produto (o produto e o agente WhatsApp), mas e o
ponto de controle/demonstracao do legado.

## 2. Objetivo

Promover o console validado no POC para `implementation/ui`: uma SPA React + Vite +
TypeScript usando **somente componentes shadcn**, consumindo a API legada via gateway
(`/api`), com servico `frontend` no compose e rota `/` no reverse proxy (ADR-0006).

Sem TDD: e um extra de demonstracao, fino e desacoplado por contrato (OpenAPI/REST).
A garantia vem do build (tsc estrito + vite) e do smoke e2e no compose.

## 3. Escopo

- `ui/`: app Vite (React 19 + TS), Tailwind v4, shadcn (preset Nova), cliente REST tipado.
- Telas: identificacao por telefone; card do titular (PII mascarada); seletor de UCs;
  faturas (tabela com badges de status/bandeira); consulta de interrupcao por bairro;
  chamados (listar + abrir com confirmacao + handoff); indicador de saude da API.
- Empacotamento: `ui/Dockerfile` (build estatico -> nginx SPA), servico `frontend` no
  compose, gateway roteando `/` -> frontend (mantendo `/api` -> backend).

## 4. Fora de escopo

- Acoes de operador que exigem novos endpoints no backend (lancar outage, baixa de
  pagamento, KPIs, fila de handoff gerenciavel) — dependem de increments do backend.
- Autenticacao/perfis; i18n; testes unitarios de UI (este extra dispensa TDD).

## 5. Criterios de aceite

- `docker compose up -d --build` sobe `frontend` e o gateway serve a SPA em `/`.
- Buscar 555199990001 mostra Ana, suas UCs e 24 faturas; bairro Jardim das Flores
  retorna interrupcao ativa.
- Abrir chamado pela UI retorna protocolo (idempotente); telefone desconhecido informa erro.
- `npm run build` (tsc estrito + vite) passa; a UI consome `/api` na mesma origem.

## 6. Plano de validacao (sem TDD)

- Build de tipos + bundle (`npm run build`).
- Smoke e2e no compose: `GET /` (SPA), asset `/assets/*.js`, `GET /api/health`,
  `GET /api/customers?phone=...` pela mesma origem do gateway.

## 7. Riscos

- Lockfile cross-platform (deps nativas do Tailwind v4 oxide): build com `npm install`.
- Drift de contrato UI<->API: mitigado por tipos no cliente espelhando os DTOs do backend.

## 8. PR relacionado

- Branch: `feature/SPEC-002-operator-console`.
- PR #3 (em aberto): https://github.com/edgardamasceno-dev/khal-ai-challenge/pull/3
  - Console promovido do POC (5 commits graduais, sem TDD). Smoke e2e no compose:
    SPA em `/`, API em `/api`, Ana retornando pela mesma origem.
