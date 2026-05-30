# ADR-0005 - Eventos deterministicos sem LLM alimentando memoria

- Status: Accepted
- Data: 2026-05-30

## Context

Acoes do operador (lancar outage, registrar baixa de pagamento) devem gerar mensagens no WhatsApp do cliente e atualizar o que o agente sabe. Passar essas notificacoes pelo LLM seria desperdicio de token e fonte de variabilidade desnecessaria, ja que o conteudo e canonico.

Token optimization e responsabilidade nomeada da vaga Lead.

## Decision

Eventos de dominio (`OutageOpened`, `PaymentRegistered`) sao publicados no NATS (subjects proprios, prefixo `utilitycx.*`, reusando o broker do Omni) e consumidos por um **worker de notificacao** que:

1. Envia uma mensagem **determinística** (template proprio, sem LLM) via REST do Omni.
2. Grava o evento em `conversation_memory`/contexto compartilhado.

No proximo turno, o agente le esse contexto e ja sabe, por exemplo, que a fatura foi paga - sem reprocessar nada.

## Consequences

Positivas:
- Demonstra token optimization e memoria como substrato compartilhado entre fluxo determinístico e agente.
- Notificacoes previsiveis e testaveis (sem LLM no caminho).

Negativas:
- Acopla a entrega ao NATS do Omni. Mitigado por `EventBusPort` (adapter), permitindo outro broker.
- Mensagens determinísticas sao menos "naturais". Aceitavel: clareza e auditabilidade valem mais aqui.

## Notes

Baileys (canal nao-oficial) envia texto livre; nao ha restricao de "template aprovado" da WhatsApp Business API oficial. "Template" aqui e mensagem canonica nossa.
