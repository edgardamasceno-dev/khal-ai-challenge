# ADR-0007 - Runtime e autenticacao do agente: Claude Code (sem key dedicada)

- Status: Accepted
- Data: 2026-05-30
- Supersede (em parte): ADR-0006 (item de credencial do hardening)

## Context

O agente roda no Genie, que **spawna o Claude Code** (doc 09: "Orquestracao: Genie + Claude Code"; o desafio pede "Processar com Claude via Genie"). O ADR-0006 fixou, no hardening da sandbox, *"so a credencial do Claude (`ANTHROPIC_API_KEY` escopada)"* - dando a entender que e preciso **provisionar uma API key dedicada**.

Na pratica o Claude Code autentica com as **credenciais ja configuradas do operador** (assinatura/OAuth ou uma key que ele ja use); nao exige uma key nova so para o agente. E, para **validar o comportamento** (harness/evals), o Claude Code roda **headless** reusando essa mesma auth - mais fiel ao runtime real do que dirigir a Claude Agents SDK crua, que forcaria uma key.

## Decision

1. **Runtime do agente = Claude Code (CLI)**, spawnado pelo Genie. Autentica com as credenciais do Claude Code do operador; **nao se provisiona `ANTHROPIC_API_KEY` dedicada** apenas para o agente/harness.
2. **Harness de comportamento/evals dirige o Claude Code headless** (mesmo prompt + mesmo MCP de producao). O runner (`src/evals/run.py`) monta um **system prompt temporario** (AGENTS.md + bloco de "Contexto do canal" com o telefone do remetente, que substitui qualquer identidade citada na mensagem) e passa a **lista explicita das 8 tools** `mcp__luz-do-vale__*` em `--allowedTools`:
   ```bash
   claude -p "<mensagem do cliente>" \
     --append-system-prompt-file <sysprompt-temp.md> \
     --mcp-config agent/mcp.config.json \
     --allowedTools mcp__luz-do-vale__find_customer_by_phone \
                    mcp__luz-do-vale__list_contracts \
                    mcp__luz-do-vale__get_invoice_status \
                    mcp__luz-do-vale__get_outage_by_region \
                    mcp__luz-do-vale__create_ticket \
                    mcp__luz-do-vale__get_ticket_status \
                    mcp__luz-do-vale__request_human_handoff \
                    mcp__luz-do-vale__search_knowledge_base \
     --permission-mode bypassPermissions \
     --output-format stream-json --verbose
   ```
   O glob `mcp__luz-do-vale__*` e o tool-scoping do agente em **producao** (frontmatter / genie-wire), **nao** a flag do harness — o runner enumera as 8 tools uma a uma. O harness asserta sobre os tool calls e a resposta (tool certa, confirmacao antes de escrever, recusa de injection/acesso cruzado).
3. **No container `sandbox`** (ADR-0006, increment 5), o Claude Code usa a auth do operador de forma escopada (montada read-only, ou uma key escopada se for a forma de auth disponivel) - a forma concreta fica na SPEC do sandbox. **Egress a `api.anthropic.com` continua necessario** (o Claude Code chama a API Anthropic independente da forma de login).
4. Isto **supersede** o item de credencial do ADR-0006: a credencial na sandbox e a **do Claude Code (qualquer forma de auth)**, nao necessariamente uma API key crua dedicada.

## Consequences

Positivas:
- POC e evals rodam **sem provisionar key** (reusa o login do Claude Code).
- Maior fidelidade: producao = Claude Code via Genie, nao a SDK crua.
- Menos um segredo a gerir no host.

Negativas:
- O harness depende do **Claude Code instalado e autenticado** no ambiente do runner (em CI, exige auth do Claude Code). Consumo conta na quota do operador. Mitigacao: documentar no runbook; no sandbox, auth escopada.

## Alternatives

- **Claude Agents SDK cru com `ANTHROPIC_API_KEY` dedicada**: funciona, mas obriga provisionar/gerir uma key e e menos fiel ao runtime real. Preterido.
- **Manter ADR-0006 como estava** (key escopada obrigatoria): rejeitado - a auth do Claude Code basta; exigir key dedicada e atrito desnecessario.
