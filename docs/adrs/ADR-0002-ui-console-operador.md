# ADR-0002 - UI como console fino de operador

- Status: Accepted
- Data: 2026-05-30

## Context

O desafio e um agente de WhatsApp; uma UI web completa seria desvio de escopo. Ao mesmo tempo, recursos como **outage proativo**, **handoff humano** e **baixa de pagamento** precisam de um ponto de controle para serem demonstraveis ao vivo, e sao acoes do lado do operador da utility, nao do agente.

## Decision

Construir uma **UI fina de console de operador** (React + Shadcn/ui) pertencente ao sistema legado simulado. Escopo: visualizar clientes/faturas (read-only), lancar outage, gerenciar fila de handoff, registrar baixa de pagamento e ver KPIs. A UI consome o FastAPI via cliente gerado do OpenAPI. Nao e o produto; o agente WhatsApp continua sendo a entrega central.

## Consequences

Positivas:
- Torna outage proativo, handoff e pagamento demonstraveis na frente do avaliador.
- Vira o painel de KPIs, fechando o ciclo de qualidade (Agent Score + metricas de producao).

Negativas:
- Adiciona superficie React/TS. Mitigado por escopo minimo e cliente gerado do OpenAPI.
- Risco de inchar e roubar foco do agente. Controle: poucas telas, sem auth complexa, time-box.

## Alternatives

- **Sem UI, so scripts CLI**: menos demonstravel; perde o "wow" do outage ao vivo.
- **UI web completa (portal do cliente)**: desvia do desafio; rejeitado.
