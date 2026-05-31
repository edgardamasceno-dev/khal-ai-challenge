# ADR-0012 - Auditoria e observabilidade por tool-call MCP (best-effort, PII mascarada)

- Status: Accepted
- Data: 2026-05-31
- Entrega: T3 (observabilidade). Relaciona-se com ADR-0001 (stack/hexagonal) e o guardrail de
  acesso-só-ao-titular (SPEC-003/SPEC-004) — auditoria é puramente **observacional**.

## Context

A tabela `tool_call_audit` já existia no schema (`db/init/01-schema.sql`: `trace_id`, `chat_id`,
`tool_name`, `input_redacted` jsonb, `result_status` CHECK in `('ok','error','denied')`,
`latency_ms`, `error_code`, `created_at`), mas era **letra morta**: sem ORM e sem nenhuma escrita.
Não havia auditoria estruturada nem log por chamada de ferramenta MCP (latência, status, PII
mascarada) — justamente o gap de observabilidade citado nas vagas.

As 9 tools passam por um único funil — `CxTools` (`src/interfaces/mcp/tools.py`), exposto por
`src/interfaces/mcp/server.py`. Há, portanto, um ponto natural para instrumentar **sem tocar
tool por tool** e sem mudar assinatura/retorno das `@mcp.tool()`.

Restrições: a auditoria não pode (a) vazar PII (telefone completo, CPF em claro), (b) derrubar a
tool ou alterar seu retorno/guardrails, nem (c) introduzir acoplamento síncrono caro no caminho da
tool. O `result_status` deve respeitar o CHECK que já existe no banco — sem alterar o schema.

## Decision

Materializar a auditoria por tool-call com fronteira **best-effort** e **mascaramento determinístico**:

1. **ORM `ToolCallAuditORM`** mapeando a tabela existente (sem alterar schema/CHECK).
2. **Port `ToolCallAuditSink`** (Protocol, em `application/ports.py`) + **`AuditRecord`** (dataclass
   frozen com input já mascarado). Adapter SQL `SqlToolCallAuditSink` (`infrastructure/repositories.py`),
   com escrita autocontida (sessão/commit próprios) para não acoplar à transação de negócio.
3. **RECORDER** (`src/interfaces/mcp/audit.py`): `instrumentar()` envolve cada método-tool medindo
   `latency_ms` na própria chamada, derivando `result_status` (`ok`; `denied` quando a tool sinaliza
   negação de guardrail via `encontrado/ok/gerado=False`; `error` em exceção, com `error_code` =
   nome da exceção) e mascarando os argumentos. `AuditedCxTools` aplica o RECORDER aos 9 métodos e
   substitui a instância em `server.py` — as `@mcp.tool()` permanecem intactas.
4. **Mascaramento de PII**: telefone → sufixo dos últimos 4 dígitos (`****0001`); chaves sensíveis
   (`cpf`/`documento`) → `***`. Nunca o número completo nem CPF em claro, no registro **e** no log.
5. **Best-effort em ambos os sentidos**: falha do sink é logada e **engolida** (a tool retorna
   normalmente); se a tool levanta, o **erro original é propagado intacto** e ainda assim um registro
   `error` é produzido. Sem sink configurado, degrada para **apenas-log** (no-op de persistência).
6. **Log estruturado** (JSON via `logging`) por chamada, em paralelo à persistência, com
   `tool_name`, `result_status`, `latency_ms`, `trace_id`/`chat_id` quando presentes — sem PII.

Escopo fechado: **não** é enforcement. A auditoria nunca bloqueia/altera tool; os guardrails
continuam onde estão (determinísticos, no código).

## Consequences

- A tabela morta vira evidência de operação: latência/status/PII-mascarada por tool, persistida e
  logada. Fecha o gap de observabilidade sem stack externa.
- Testabilidade preservada pela fronteira hexagonal: `FakeSink`/`BrokenSink` cobrem registro,
  mascaramento e best-effort nos dois sentidos; integração contra `khal_test` valida insert/select
  e que o CHECK rejeita `result_status` inválido.
- Custo no caminho da tool é uma escrita best-effort com sessão curta; pode ser tornada assíncrona
  futuramente sem mudar o port. `created_at` vem do `server_default now()` do banco.
- A derivação de `denied` depende da convenção de retorno das tools (`encontrado/ok/gerado=False`);
  se uma tool nova não a seguir, cai em `ok`. Aceitável: é sinal observacional, não controle.

## Alternatives

- **Instrumentar tool por tool** (decorador em cada `@mcp.tool()`): repetitivo e fácil de esquecer
  numa tool nova. Rejeitado — o funil único de `CxTools` é o ponto certo.
- **Escrever na mesma transação/UoW da tool**: acoplaria auditoria ao negócio e um erro de
  auditoria poderia abortar/contaminar a operação. Rejeitado — quebra o best-effort.
- **OpenTelemetry/Prometheus/tracing distribuído**: fora do escopo T3 (registro estruturado +
  persistência na tabela existente). Pode vir depois atrás do mesmo port.
- **Logar input cru e mascarar só na exibição**: risco de PII em repouso/logs. Rejeitado —
  mascaramento na origem (`input_redacted`), antes de persistir/logar.
