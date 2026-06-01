# ADR-0019 - Resumo de thread no fechamento: `SummarizerPort` + adapter Haiku opt-in com fallback extrativo determinístico (default)

- Status: Accepted
- Data: 2026-05-31
- SPECs: SPEC-028 (resumo de thread no fechamento de ticket/handoff). Relaciona-se com
  ADR-0013 (fronteira de memória — `kind=resumo` é tag no JSONB `valor`, não uma fonte nova),
  ADR-0005 (escrita determinística sem LLM no caminho crítico), ADR-0004/ADR-0014 (Strategy
  plugável e prefixo cacheável), SPEC-016/SPEC-020 (pontos de fechamento), SPEC-027 (memória
  por `titular_id`).

## Context

Ao encerrar um atendimento — **ticket resolvido** (SPEC-020) ou **handoff devolvido à IA**
(SPEC-016) — não há nada que condense **o que aconteceu** na conversa. A `conversation_memory`
guarda apenas **fatos determinísticos de sistema** (pagamento confirmado, outage aberta/encerrada
— ADR-0005), nunca um panorama do fio conversacional. Em cold-start (a sessão Genie reseta,
ADR-0013), o agente perde o contexto já tratado; o operador, ao reabrir a fila, não tem um TL;DR.

Resumir é tarefa natural de LLM. Mas duas restrições do projeto pesam:

1. **Sem LLM no caminho crítico (ADR-0005):** o ticket precisa resolver e o cliente ser notificado
   **mesmo se** a API de resumo estiver fora/lenta, a dep não instalada, ou o egress bloqueado.
2. **Não inflar a superfície MCP / cache (R-07):** transformar o resumo numa 13ª tool exposta
   mexeria na `allowlist.py`, invalidaria o cache de tool-defs e exigiria teste de contrato novo.

Precisamos do resumo **bom quando dá** (LLM) e **sempre** de um resumo útil (determinístico), sem
acoplar o fechamento a uma chamada de rede nem à disponibilidade de uma chave/dep.

## Decision

Introduzir o resumo de thread como **estratégia plugável atrás de uma porta**, com **fallback
determinístico como default**, disparado **best-effort** no fechamento:

1. **`SummarizerPort` (porta, `application/ports.py`)** — `summarize(mensagens, *, max_chars) -> str`.
   Contrato: devolve resumo **não-vazio** ou **levanta `SummarizerError`** (nunca string vazia
   silenciosa). Padrão **Strategy/Adapter**: o LLM fica **atrás** da porta.

2. **Fallback extrativo determinístico (DEFAULT), `domain/conversation/summarize.py`** —
   `resumo_extrativo`: heurística pura (1ª msg do cliente + últimas N trocas, prefixadas por
   `[cliente]`/`[agente]`, truncadas em `max_chars`). Sem rede, idempotente, 100% unit-testável.
   É o que roda quando **não** há `summarizer`, quando ele **falha** ou quando devolve vazio.

3. **Adapter LLM Haiku (OPT-IN), `infrastructure/summarize/anthropic_summarizer.py`** —
   `AnthropicHaikuSummarizer`: Claude Haiku via SDK `anthropic` (import **lazy**, padrão
   `minio`/`weasyprint`), system prompt fixo com `cache_control: ephemeral` (prefixo cacheável,
   ADR-0014). **Qualquer** exceção/empty → `SummarizerError`. Dep `anthropic` é **opcional**
   (`[project.optional-dependencies].summarize`).

4. **`ThreadSummaryService` (orquestrador, `application/services.py`)** — resolve titular, lê a
   transcrição (`ChatTranscriptPort`), aplica a estratégia (LLM → senão extrativo) e grava em
   `conversation_memory` via `upsert` com `chave="resumo.<protocolo|ts>"` e
   `valor={"texto","kind":"resumo","fonte":"haiku"|"extrativo","em":iso}` + `titular_id` (SPEC-027).
   `summarize_thread_safe` é o wrapper **best-effort** (no-op sem telefone; engole toda exceção).

5. **Disparo no fechamento (serviço, não tool):** `TicketingService` recebe um `thread_summary`
   opcional e chama `summarize_thread_safe` em `resolve_ticket` (por protocolo) e `resume_handoff`
   (por ts). **Não** há tool MCP nova — a `allowlist`/cache de tool-defs fica intacta (R-07).

`kind=resumo` é **tag no JSONB `valor`**, sem coluna/entidade nova (ADR-0013): o resumo é mais um
fato em `conversation_memory`, distinto da transcrição (Omni) e da sessão (Genie).

## Consequences

**Positivas**
- O fechamento é **sempre** resumido, com ou sem LLM/dep/egress. "Sem LLM no caminho crítico"
  respeitado por construção: o default é determinístico e o LLM é best-effort atrás da porta.
- Trocar de provedor de LLM (ou melhorar o adapter) **não** toca o serviço nem o domínio.
- Zero impacto na superfície MCP: sem 13ª tool, sem invalidar o cache de tool-defs, sem teste de
  contrato novo. Memória por `titular_id` (SPEC-027) e idempotência por chave reaproveitadas.
- Fallback extrativo é unit-testável sem mock; o serviço é testável com `FakeSummarizer`
  (sucesso) e um summarizer que levanta (fallback), provando que a falha **não** propaga.

**Negativas / trade-offs**
- O resumo **extrativo** é mais pobre que um abstrativo (recorta trechos, não parafraseia). É o
  preço de não depender de rede; o Haiku, quando habilitado, eleva a qualidade.
- Habilitar o LLM exige **config ao vivo** (injetar o adapter no composition root, instalar
  `[summarize]`, `ANTHROPIC_API_KEY`/auth + egress Anthropic). Pendência de runtime, não de código.
- Nova dep opcional `anthropic`: mantida **fora** do core e do caminho crítico para não pesar no
  lock/egress padrão.

## Alternatives

- **Tool MCP `summarize_thread` exposta (rejeitada para o MVP):** mexeria na allowlist e no cache de
  tool-defs (R-07) e exigiria teste de contrato. Disparo no serviço entrega o mesmo efeito sem isso;
  expor como 13ª tool fica para uma SPEC futura, se houver caso de uso do agente chamá-la sob demanda.
- **LLM síncrono no caminho crítico (rejeitada):** viola ADR-0005; um timeout/queda da API
  bloquearia o fechamento e a notificação ao cliente.
- **Só extrativo, sem porta para LLM (rejeitada):** simples, mas teto de qualidade baixo e sem
  caminho de evolução; a porta custa pouco e abre o opt-in.
- **Resumo no worker/assíncrono (adiada):** desacoplaria de vez do fechamento, mas adiciona um
  subject/consumer e latência de propagação; o best-effort inline já satisfaz o requisito com menos
  peças. Pode ser revisitado se o volume justificar.
