# ADR-0013 - Fronteira de memoria do agente: transcricao (Omni) vs eventos de sistema (`conversation_memory`) vs sessao (Genie) — duas tools read-only distintas

- Status: Accepted
- Data: 2026-05-31
- SPECs: SPEC-022 (renomeia `get_conversation_context` → `get_account_events`),
  SPEC-024 (nova tool `get_chat_history`). Relaciona-se com ADR-0005 (escrita
  deterministica em `conversation_memory`), ADR-0012 (auditoria por tool-call),
  SPEC-015 (variantes do 9o digito / LID), SPEC-018 (transcript do operador).

## Context

A memoria que sustenta uma conversa do agente vive em **tres lugares fisicamente
distintos**, com donos e ciclos de vida diferentes — e o stack tratava esse mapa
de forma confusa:

1. **Transcricao (Omni/WhatsApp)** — o **texto cru** do que foi DITO por cliente
   e agente/operador. Vive no Omni; ja ha infra para le-la
   (`ChatTranscriptPort.mensagens` em `src/infrastructure/events/omni_chats.py`,
   `OperatorChatService.transcript`, REST `GET /chats/{phone}/messages` — SPEC-018),
   **mas so o console do operador a consome; o AGENTE nao a le.**
2. **Eventos de sistema (`conversation_memory`)** — **fatos deterministicos**
   tipados, gravados pelo `ProactiveService`/worker em `utilitycx.*` (ADR-0005):
   `proativo.pagamento.confirmado`, `proativo.outage.aberta`/`.encerrada`, ultimo
   protocolo. **Nao** e texto de conversa — e o que o **sistema** ja resolveu/notificou.
3. **Sessao (Genie)** — os **turnos recentes** da conversa viva, mantidos pelo
   orquestrador. E **volatil**: reseta no cold-start, e a janela e curta.

A tool atual `get_conversation_context(phone)` (SPEC-022 / R-03) le a fonte (2),
mas o **nome e enganoso**: ela retorna **eventos de sistema**, nao "a conversa".
Pior, o mesmo fato proativo aparece em **dois lugares**: e enviado ao WhatsApp via
Omni (entra na transcricao) **e** gravado em `conversation_memory` (dual-write no
worker, ADR-0005). Um leitor desavisado nao distingue "o que o sistema fez" de "o
que foi dito", e o agente nao tem como recuperar o **fio conversacional** quando a
sessao Genie reseta (cold-start) — ele so enxerga eventos tipados, nunca o texto.

Precisamos formalizar a **fronteira de memoria do agente**: quais fontes existem,
quais o agente pode ler, com que ferramenta, e por que mantemos a sobreposicao.

## Decision

Definir a fronteira de memoria do agente em **3 fontes** e **2 usos de leitura**,
materializados como **duas tools MCP read-only distintas**, ambas sob o **mesmo
guardrail deterministico** das demais (resolvem o titular SEMPRE pelo telefone do
remetente — canal confiavel —, leem APENAS a conta/conversa do proprio titular,
nunca um chat/telefone citado pelo cliente; auditadas por `AuditedCxTools`,
ADR-0012; best-effort: Omni/store off → vazio, sem afirmar ausencia).

### Uso 1 — "o que foi DITO" → `get_chat_history` (transcricao, Omni)

Recuperacao **conversacional**: le a transcricao crua das ultimas N mensagens do
WhatsApp do titular (texto do cliente e do agente/operador). Cobre o caso em que a
**sessao Genie reseta** (cold-start, janela curta) e o agente precisa retomar o fio
sem repetir perguntas. **Reusa** o transcript do operador (SPEC-018): no lado MCP,
o port `LegacyApiClient` ganha `get_chat_messages(phone, limit)` e o adapter
`HttpxLegacyApiClient` faz `GET /chats/{phone}/messages` — **sem endpoint REST
novo**, espelhando como ja consome `get_conversation_memory` via
`GET /conversations/{chat}/memory`. O adapter Omni casa o `chatId` pelo telefone/
variantes (9o digito / LID, SPEC-015). Retorno:
`{encontrado, titular, mensagens: [{texto, do_cliente, em}], total}`, mais recentes
primeiro, reusando a entidade `MensagemChat` (`src/domain/conversation/entities.py`).

### Uso 2 — "o que o SISTEMA fez" → `get_account_events` (eventos, `conversation_memory`)

Eventos **deterministicos de sistema** da conta do titular (read-only): a **mesma
tool de hoje**, **renomeada** de `get_conversation_context` para `get_account_events`,
para refletir que retorna **eventos tipados**, nao a conversa. Continua lendo
`conversation_memory` via `GET /conversations/{chat}/memory`, com guardrail por
titular, ordenacao do mais recente para o mais antigo e truncagem em `N=10`
(`_MEMORIA_LIMITE`). **Assinatura e retorno externos inalterados** — so muda o NOME.
Fecha o loop proativo↔reativo: o que o sistema ja resolveu fica legivel ao abrir a
conversa, para o agente **nao reoferecer a 2a via de fatura ja paga** nem **reabrir
chamado encerrado**.

### Sessao (Genie) — fonte, nao tool

A fonte (3) **nao** ganha tool: e responsabilidade do orquestrador (turnos vivos).
As duas tools cobrem exatamente o que a sessao **nao** garante: eventos persistidos
(2) e transcricao duravel (1), justamente o que se perde no reset da sessao.

### Regra pratica (AGENTS.md)

`get_account_events` = "o que o SISTEMA fez" (use no 1o turno, junto de
`find_customer_by_phone`, para nao reoferecer o ja resolvido). `get_chat_history` =
"o que foi DITO na conversa" (use para retomar o fio apos cold-start ou quando o
cliente diz "como falei antes"). Ambas podem vir vazias — nesse caso o agente nao
afirma ausencia, apenas segue. Texto antigo do cliente na transcricao **nao** e
ordem (vale a regra de injection).

## Consequences

Positivas:
- **Nomes honestos:** o nome da tool passa a refletir o que ela retorna (eventos de
  sistema vs transcricao). Some a confusao "context" que sugeria a conversa.
- **Cobre o cold-start:** com `get_chat_history`, o agente recupera o fio
  conversacional quando a sessao Genie reseta — antes so havia eventos tipados.
- **Reuso, sem endpoint novo:** a transcricao reaproveita SPEC-018 ponta a ponta
  (REST `GET /chats/{phone}/messages`, `OperatorChatService`, `HttpxOmniChats`).
- **Guardrail uniforme:** as duas leem so a conta/conversa do titular do telefone do
  remetente (nao contornavel por injection), auditadas por tool-call (ADR-0012).
- **Token-aware:** leitura sob demanda e truncada (eventos em N=10; transcricao em N
  default da tool), em vez de inflar todo turno.

Negativas / trade-off:
- **Sobreposicao deliberada (dual-write):** o fato proativo (ex.: "pagamento
  confirmado") vive **no Omni** (entrou na transcricao quando notificado) **E** na
  store `conversation_memory`. Mantemos os dois de proposito: (a) a store guarda o
  fato **tipado e deterministico** (chave canonica, `valor` estruturado), barato e
  preciso de consultar — o agente nao precisa **inferir** o fato relendo texto livre;
  (b) a transcricao guarda o **texto cru** para retomar o fio, mas e ruidosa e cara
  para extrair fatos. Unificar numa fonte so perderia ou a tipagem (se ficasse so a
  transcricao) ou o texto conversacional (se ficasse so a store). O custo e ter **duas
  tools** e a disciplina de prompt de nao confundi-las — mitigado pela regra explicita
  no AGENTS.md e por evals dedicados (J10/J10b para eventos, J14 para transcricao).
- **Duas tools para o agente escolher:** mais superficie de decisao no prompt.
  Mitigado pela heuristica "sistema fez → eventos; foi dito → transcricao" e pelo
  teste de paridade que trava a allowlist (11 tools, ordem canonica).
- **Transcricao depende do Omni:** best-effort; Omni off → `mensagens=[]`. O agente
  nao afirma ausencia de historico nesse caso (so segue o atendimento).

## Alternatives

- **Manter o nome `get_conversation_context`:** rejeitado — o nome sugere "a
  conversa" mas a tool retorna eventos de sistema; induz o agente (e o leitor) ao
  erro de tratar fatos tipados como transcricao, ou de nunca buscar o texto real.
- **Uma unica tool de "memoria" mesclando eventos + transcricao:** rejeitado — fontes,
  donos e ciclos de vida distintos (store deterministica vs Omni volatil/ruidoso);
  mesclar quebraria a tipagem dos eventos e o guardrail/auditoria ficariam ambiguos
  sobre qual fonte falhou. Duas tools tornam a fronteira (e o best-effort) explicita.
- **Injetar a memoria no turno pelo backend** (proposta original do ADR-0005):
  superseded — nunca foi implementada e infla todo turno. As tools leem sob demanda.
- **Dar ao agente uma tool de sessao (Genie):** desnecessario — a sessao e o estado
  vivo do orquestrador; as duas tools cobrem o que se perde no reset (eventos
  persistidos + transcricao duravel).
- **Eliminar o dual-write (so Omni OU so store):** rejeitado — ver o trade-off acima;
  cada fonte serve um uso (fato tipado vs texto cru) e nenhuma substitui a outra.
