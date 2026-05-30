# Console do operador — Luz do Vale

UI fina (React + Vite + TypeScript, **apenas componentes shadcn**) que consome a API
legada (SPEC-001) pela mesma origem do gateway (`/api`). Não é o produto — é o ponto de
controle/demonstração do sistema legado (ADR-0002, SPEC-002).

## O que faz

- Identifica o titular por telefone (`find_customer_by_phone`).
- Card do titular com PII mascarada + seletor de unidades consumidoras.
- Faturas por UC (tabela com badges de status e bandeira tarifária).
- Consulta de interrupção por bairro (`get_outage_by_region`).
- Chamados: listar, abrir com confirmação (`create_ticket`, idempotente) e solicitar handoff.
- Indicador de saúde da API (`/health`).

## Stack

Vite + React 19 + TypeScript · Tailwind v4 · shadcn (preset Nova, base Neutral) · sonner.

## Desenvolvimento

```bash
npm install
npm run dev        # requer a API em /api (use `make compose-up` na raiz, ou um proxy)
npm run build      # type-check estrito + bundle de produção
```

Em produção roda containerizado: `Dockerfile` faz o build estático e serve via nginx;
o gateway roteia `/` para este serviço. Suba tudo com `make compose-up` na raiz do repo.

> Sem TDD por decisão (extra de demonstração); a garantia vem do `tsc` estrito + build
> e do smoke e2e no compose. O cliente em `src/lib/api.ts` espelha os DTOs do backend.
