# Sandbox — runtime Omni/Genie do agente CX (SPEC-007)

Increment 5 do **ADR-0006**: o agente `luz-do-vale` atende no **WhatsApp** via **Omni**
(Baileys) orquestrado pelo **Genie** (que spawna o Claude Code), num container isolado que
alcança o negócio **apenas via MCP**. Detalhes e validações: `docs/specs/SPEC-007-*`.
Passo a passo de operação: `sandbox/RUNBOOK.md`.

## Pré-requisito: clones pinados (untrusted, doc 07)

Os repos `genie`/`omni` são **não-confiáveis para execução** e **não** são versionados
aqui. Clone-os em `sandbox/libs/` (gitignored) nos commits pinados antes de buildar:

```bash
git clone https://github.com/automagik-dev/genie sandbox/libs/genie
(cd sandbox/libs/genie && git checkout a407a2e2)
git clone https://github.com/namastexlabs/omni  sandbox/libs/omni
(cd sandbox/libs/omni  && git checkout fe155b81)
```

## Build

A partir da **raiz do repo de entrega** (`implementation/`):

```bash
docker build -f sandbox/Dockerfile -t khal-sandbox:base .   # Genie+Omni+NATS+Claude Code
docker build -t khal-egress-proxy sandbox/egress            # proxy com allowlist
```

## Subir (override do compose real)

```bash
docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml up -d
```

Sobe `database` + `seed` + `backend` + `mcp-server` (em `mcpnet`) + `egress-proxy` +
`sandbox`. O `sandbox` fica em `sleep infinity` (operador dirige — ver RUNBOOK).

## Arquivos

| Arquivo | Papel |
|---|---|
| `Dockerfile` | imagem `khal-sandbox:base` (clones pinados, non-root, telemetria off) |
| `compose.sandbox.yml` | override: `egress-proxy` + `sandbox` + redes internas |
| `egress/` | proxy tinyproxy com **allowlist** (Anthropic + WhatsApp) |
| `sandbox-up.sh` | orquestra Postgres-genie + NATS(JS) + Omni API + `genie serve` |
| `enable-media.sh` / `disable-media.sh` | **opt-in** da rota de mídia p/ o anexo PDF (SPEC-019/ADR-0010) |
| `genie-wire.sh` | monta o agente `luz-do-vale` (frontmatter + persona) + MCP user-scope |
| `agent/luz-do-vale.frontmatter.yaml` | **tool-scoping** (allow só MCP + `Bash(omni:*)`) |
| `verify-scoping.ts` | prova determinística do comando escopado do Claude Code |
| `RUNBOOK.md` | operação: login, wiring, daemons, E2E interno e WhatsApp real |

## Guardrails (validados — ver SPEC-007)

- **Rede só-MCP:** alcança `mcp-server`; **não** `backend`/`database`.
- **Tool-scoping:** Claude Code só com `mcp__luz-do-vale__*` + `Bash(omni:*)`.
- **Egress allowlist:** só Anthropic + WhatsApp (relaxado p/ Baileys via rede direta — RUNBOOK 6.0).
- **Auth:** `claude login` persistido em volume `claude-home`, sem API key (ADR-0007).
