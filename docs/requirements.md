# Requisitos - khal-ai-challenge

Dominio: atendimento de CX de uma distribuidora de energia ficticia ("Luz do Vale") no WhatsApp. RF = o que o sistema faz; RNF = qualidades/restricoes. IDs sao estaveis e referenciados nas SPECs.

## Requisitos funcionais (RF)

| ID | Requisito |
| --- | --- |
| RF-01 | Receber mensagens de WhatsApp via Omni e responder pelo mesmo canal. |
| RF-02 | Identificar o titular pelo telefone do remetente. |
| RF-03 | Consultar contratos, UCs e status de fatura do titular. |
| RF-04 | Emitir segunda via e enviar o PDF da fatura no WhatsApp. |
| RF-05 | Consultar status de interrupcao (outage) por regiao/bairro. |
| RF-06 | Abrir chamado com confirmacao explicita e devolver protocolo + SLA. |
| RF-07 | Consultar status de chamado por protocolo. |
| RF-08 | Responder duvidas consultando a base de conhecimento (RAG), citando a fonte. |
| RF-09 | Escalar para humano (handoff) quando nao puder resolver. |
| RF-10 | Notificar proativamente (outage aberto, pagamento recebido) sem acionar o LLM. |
| RF-11 | Manter memoria/contexto curto por conversa (`chatId`). |

## Requisitos nao-funcionais (RNF)

| ID | Requisito |
| --- | --- |
| RNF-01 | **Execucao reprodutivel e 100% containerizada** via `docker compose` (rollout gradual, ver ADR-0006). |
| RNF-02 | **Least-privilege**: agente roda em sandbox isolada; so a credencial do **Claude Code** (auth reusada, sem key dedicada - ver ADR-0007); sem segredos reais fora do escopo (ver ADR-0006, doc 07). |
| RNF-03 | **Isolamento**: o agente so alcanca o negocio via MCP (com guardrails); sem acesso direto a banco/storage. |
| RNF-04 | **Observabilidade**: logs JSON com `traceId`, `chatId`, `toolName`, `latencyMs`, `resultStatus`; auditoria de tool calls. |
| RNF-05 | **Seguranca/PII**: sem PII real; redacao de segredos em log; validacao de input em toda ferramenta/endpoint (ver docs/security). |
| RNF-06 | **Determinismo**: seed reprodutivel (mesma seed -> mesmo dataset) e idempotente. |
| RNF-07 | **Robustez**: tratamento de erro e degradacao segura quando uma dependencia (API/DB) falha. |
| RNF-08 | **Idempotencia**: acoes de escrita (chamado, baixa de pagamento) nao duplicam. |
| RNF-09 | **Qualidade**: evals com Agent Score (meta >= 85), regressao bloqueia PR; lint/typecheck/testes verdes no HEAD. |
| RNF-10 | **Performance**: latencia de ferramenta logada (alvo p95 por ferramenta definido nos evals). |

## Rastreabilidade

- ADRs: `docs/adrs/`. RNF-01/02/03 -> ADR-0006; RNF-02 (credencial) -> ADR-0007; RF-04 -> ADR-0003; RF-08 -> ADR-0004; RF-10/RF-11 -> ADR-0005.
- SPECs: `docs/specs/` linkam RF/RNF cobertos e o PR correspondente.
