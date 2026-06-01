# ADR-0005 - Eventos deterministicos sem LLM alimentando memoria

- Status: Accepted (revisado em 2026-05-31 — leitura da memoria via tool MCP read-only)
- Data: 2026-05-30
- Revisao: 2026-05-31 (R-03 / SPEC-022). A promessa de **injecao da memoria no turno pelo
  backend** e marcada como **superseded**; a leitura passa a ser cumprida por uma **tool MCP
  read-only** (`get_account_events`, originalmente `get_conversation_context`). A escrita
  deterministica (worker/`ProactiveService` em `utilitycx.*`) permanece **inalterada e valida**.
- Revisao: 2026-05-31 (ADR-0013 / SPEC-022). A tool de leitura e **renomeada** de
  `get_conversation_context` para `get_account_events` para refletir que retorna **eventos
  deterministicos de sistema** (nao a transcricao da conversa). Assinatura/retorno externos
  inalterados — so muda o nome. A fronteira de memoria (transcricao Omni vs eventos desta store
  vs sessao Genie) e a nova tool de transcricao `get_chat_history` ficam formalizadas no ADR-0013.

## Context

Acoes do operador (lancar outage, registrar baixa de pagamento) devem gerar mensagens no WhatsApp do cliente e atualizar o que o agente sabe. Passar essas notificacoes pelo LLM seria desperdicio de token e fonte de variabilidade desnecessaria, ja que o conteudo e canonico.

Token optimization e responsabilidade nomeada da vaga Lead.

## Decision

Eventos de dominio (`OutageOpened`, `PaymentRegistered`) sao publicados no NATS (subjects proprios, prefixo `utilitycx.*`, reusando o broker do Omni) e consumidos por um **worker de notificacao** que:

1. Envia uma mensagem **determinística** (template proprio, sem LLM) via REST do Omni.
2. Grava o evento em `conversation_memory`/contexto compartilhado.

> **Revisao 2026-05-31 (R-03 / SPEC-022) — leitura agora via tool MCP read-only.**
>
> A formulacao original (abaixo) era: *"esse contexto chega ao agente pela entrada confiavel do
> canal; a leitura fica no backend (REST / `MemoryService`), que injeta o contexto no turno"*.
> Essa **injecao no backend nunca foi implementada** — o spawn do agente so passa o `AGENTS.md`
> estatico, sem injetar a memoria do turno. **Decisao revista:** a leitura passa a ser cumprida
> por uma **tool MCP read-only** `get_account_events(phone)` (originalmente
> `get_conversation_context`, renomeada pelo ADR-0013) que o agente chama no **abrir** da
> conversa (`find_customer_by_phone` **e** `get_account_events`, em paralelo).
> A tool resolve o titular **sempre** pelo telefone do remetente e le **apenas** a memoria do
> proprio titular, sob o **mesmo guardrail de acesso por telefone** das demais tools (auditada
> por `AuditedCxTools`, ADR-0012). Assim o agente sabe, por exemplo, que a fatura ja foi paga —
> e **nao** reoferece a 2a via dela. A parte **"injecao no backend"** fica **superseded**; todo
> o resto deste ADR (escrita determinista sem LLM em `utilitycx.*`, broker via `EventBusPort`)
> permanece valido. **Chave da memoria:** hoje `chat_id == telefone E.164`; **R-12 / SPEC-022**
> migra para `titular_id` (corrige fragmentacao multi-UC e LID vs. MSISDN), e a tool passa a
> consumir a chave correta **sem mudar sua assinatura/retorno externos** — so muda o adapter REST.
>
> _Texto original (mantido como registro historico):_ No proximo turno, esse contexto gravado em
> `conversation_memory` chega ao agente pela **entrada confiavel do canal** (Omni): o agente
> **nao** le a memoria por uma tool MCP propria (nao ha tool de memoria) - a leitura fica no
> **backend** (REST / `MemoryService`), que injeta o contexto no turno. Assim o agente ja sabe,
> por exemplo, que a fatura foi paga - sem reprocessar nada.

## Consequences

Positivas:
- Demonstra token optimization e memoria como substrato compartilhado entre fluxo determinístico e agente.
- Notificacoes previsiveis e testaveis (sem LLM no caminho).
- **(revisao 2026-05-31)** A leitura por **tool MCP read-only** fecha o loop proativo↔reativo
  **sob o mesmo guardrail de acesso por telefone** das demais tools (nao contornavel por
  injection), auditada por tool-call (ADR-0012), e mantem a **escrita 100% determinista**. O
  agente le a memoria sob demanda (no abrir) em vez de receber um contexto inflado a cada turno
  — alinhado com token optimization.

Negativas:
- Acopla a entrega ao NATS do Omni. Mitigado por `EventBusPort` (adapter), permitindo outro broker.
- Mensagens determinísticas sao menos "naturais". Aceitavel: clareza e auditabilidade valem mais aqui.
- **(revisao 2026-05-31)** A leitura depende do agente **chamar** a tool no abrir da conversa
  (regra de prompt no `AGENTS.md`), e nao mais de uma injecao garantida pelo backend. Mitigado
  por: (a) regra explicita de abertura no `AGENTS.md`; (b) cenarios de eval que exigem a chamada
  de `get_account_events` no 1o turno (R-03); (c) guardrail deterministico no codigo da
  tool, independente do prompt.

## Notes

Baileys (canal nao-oficial) envia texto livre; nao ha restricao de "template aprovado" da WhatsApp Business API oficial. "Template" aqui e mensagem canonica nossa.
