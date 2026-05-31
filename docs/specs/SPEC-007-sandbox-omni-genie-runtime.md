# SPEC-007 - Runtime do sandbox (wiring Omni/Genie + agente CX)

- Status: Approved (2026-05-30) — PR #11
- Versao alvo: 0.8.0 (increment 5 do ADR-0006: o agente atende no WhatsApp)
- ADRs: ADR-0006 (Docker Compose + sandbox), ADR-0007 (Claude Code, sem key). Sem ADR novo.

## 1. Problema

As SPECs 000–006 entregam o negocio (banco, API legada, MCP, agente CX, KB, personas) e
o agente foi validado por evals (`claude -p` direto). Falta o **canal real**: o agente
atendendo no **WhatsApp** via **Omni** (Baileys) orquestrado pelo **Genie** (que spawna o
Claude Code), num **sandbox isolado** que alcanca o negocio **apenas via MCP**. Esse runtime
foi prototipado e validado E2E em `poc/sandbox`; esta SPEC o **formaliza na entrega**.

## 2. Objetivo

Versionar, em `sandbox/`, a imagem e a orquestracao que poem o agente `luz-do-vale` no ar
no WhatsApp, com os guardrails determinISticos: **rede so-MCP**, **tool-scoping** do Claude
Code, **egress allowlist** e **auth persistida** (sem API key, ADR-0007). Os clones
**untrusted** (genie/omni, doc 07) permanecem **fora do git** (`sandbox/libs/`, gitignored).

### Decisoes de arquitetura (pinadas aqui; nao contrariam ADRs)
- **Imagem unica do sandbox** (`sandbox/Dockerfile`) a partir dos clones **pinados**
  (`genie@a407a2e2`, `omni@fe155b81`), `--ignore-scripts`, telemetria off, non-root.
  Binarios criticos (NATS, `@embedded-postgres`) **bakeados** no build (egress allowlist
  bloquearia o download em runtime).
- **Genie sem dependencias globais proibidas** (doc 07): sem `genie setup` interativo
  (`~/.genie/config.json` com `setupComplete:true` bakeado) e sem `pgserve`/`autopg` global
  (Genie em **force-TCP** contra um Postgres comum em `:19642`).
- **Tool-scoping = camada 1 dos guardrails**: o agente CX e um agente Genie
  (`agents/luz-do-vale/AGENTS.md`) cujo **frontmatter** restringe o Claude Code a
  `mcp__luz-do-vale__*` + `Bash(omni:*)` (resposta); `--disallowedTools` em
  WebFetch/WebSearch/escrita/Task. A persona vem de `implementation/agent/AGENTS.md`.
- **Rede so-MCP** (ADR-0006): redes internas (`mcpnet`/`egressnet`); o sandbox alcanca o
  negocio **apenas** via `mcp-server`; sem rota a `backend`/`database`.

## 3. Escopo

- `sandbox/Dockerfile` — imagem `khal-sandbox:base` (Genie+Omni+NATS+Claude Code).
- `sandbox/compose.sandbox.yml` — **override** do `docker-compose.yml` real: adiciona
  `egress-proxy` + `sandbox` + redes internas; poe o `mcp-server` em `mcpnet`.
- `sandbox/egress/` — proxy com **allowlist** (Anthropic `anthropic.com`/`claude.com`/
  `claude.ai` + WhatsApp `whatsapp.net`/`whatsapp.com`).
- `sandbox/sandbox-up.sh` — orquestra os daemons: Postgres-do-genie (`:19642`) → NATS
  (`:4222`, JetStream) → Omni API (`:8882`) → `genie-wire.sh` → `genie serve --headless`.
- `sandbox/genie-wire.sh` — monta `agents/luz-do-vale/AGENTS.md` (frontmatter + persona) e
  registra o MCP no Claude Code (escopo user, volume `claude-home`).
- `sandbox/agent/luz-do-vale.frontmatter.yaml` — camada de tool-scoping.
- `sandbox/verify-scoping.ts` — prova, via as funcoes do Genie, que o comando do Claude Code
  sai escopado (so MCP + `Bash(omni:*)`; WebFetch/WebSearch/escrita bloqueados).
- `sandbox/RUNBOOK.md` — passo a passo: stack → `claude login` → wiring → daemons → E2E
  interno (NATS) → **E2E WhatsApp real** (instancia → pairing code → connect → LID-seed).
- `sandbox/libs/{genie,omni}` — clones **pinados**, **gitignored** (pre-requisito de build).

## 4. Fora de escopo

- Versionar os clones genie/omni (untrusted, doc 07 — ficam em `sandbox/libs/`, ignorados).
- Resolucao **LID→telefone** no Omni (`chat_id_mappings`) — demo usa persona chaveada pelo
  LID (SPEC-006); a resolucao real fica como follow-up.
- Persistencia da sessao do WhatsApp/Omni em volume (hoje efemera; refinamento futuro).
- `executor: 'sdk'` do Genie — usamos o `tmux` (Claude Code CLI, ADR-0007).

## 5. Pre-requisitos (build)

Os clones **pinados** vivem em `sandbox/libs/` (gitignored). Para buildar:

```bash
git clone <genie> sandbox/libs/genie && (cd sandbox/libs/genie && git checkout a407a2e2)
git clone <omni>  sandbox/libs/omni  && (cd sandbox/libs/omni  && git checkout fe155b81)
docker build -f sandbox/Dockerfile -t khal-sandbox:base .
docker build -t khal-egress-proxy sandbox/egress
```

## 6. Topologia e guardrails (validados)

```
WhatsApp → Omni(Baileys) → NATS → genie omni-bridge → Claude Code (escopado)
   → MCP mcp__luz-do-vale__* → backend → Postgres → omni say → WhatsApp
```

- **Rede so-MCP**: `docker exec khal-sandbox` alcanca `mcp-server` (406) e **nao**
  `backend`/`database` (000). Validado.
- **Tool-scoping**: `verify-scoping.ts` asserta o comando escopado. Validado.
- **MCP conectando**: `claude mcp get luz-do-vale` → `✓ Connected` (mcpnet). Validado.
- **Auth**: `claude login` persiste em `claude-home` (volume, nao versionado).
- **E2E interno**: publicar `omni.message` → bridge → agente → **tool-calls no MCP** →
  reply. Validado (11 tool-calls, dados reais do seed).
- **E2E WhatsApp real**: instancia pareada (pairing code), `omni connect`, mensagem do
  cliente → agente respondeu por WhatsApp com dados reais (`POST /messages/send → 201`).
  Validado.

## 7. Riscos e mitigacao

- **WSS do Baileys ignora `HTTP_PROXY`** e o sandbox nao tem internet direta → sem QR.
  Mitigacao (RUNBOOK 6.0): rede **nao-interna** so para o sandbox; mantem `backend`/`database`
  inalcancaveis (so-MCP preservado), relaxa o allowlist para a infra omni/Baileys; o **agente**
  segue contido pelo tool-scoping.
- **Auth do Claude Code TUI atrela ao container**: apos `recreate`, refazer `claude login`
  (o `claude -p`/headless segue valido). Documentado no RUNBOOK.
- **WhatsApp manda LID, nao telefone**: persona chaveada pelo LID (demo); follow-up resolver
  LID→telefone no Omni.
- **Clones untrusted** (doc 07): so leitura/estudo; build `--ignore-scripts`, telemetria off,
  non-root; nunca instaladores globais nem `curl|bash`.

## 8. Criterios de aceite

- `khal-sandbox:base` builda a partir de `sandbox/libs/` (clones pinados) e sobe via o
  override do compose real.
- Guardrails validados: rede so-MCP, tool-scoping (verify-scoping), MCP `✓ Connected`.
- RUNBOOK reproduz o E2E (interno e WhatsApp real).
- Clones genie/omni **nao** versionados; nenhum numero real de demo no repo.
