# ADR-0006 - Execucao via Docker Compose com sandbox unica

- Status: Accepted
- Data: 2026-05-30

## Context

O desafio avalia setup reproduzivel (doc 02: "docker-compose, scripts"). E o doc 07 (supply chain) exige que Omni/Genie rodem isolados, sem credenciais reais no host. Em vez de "sandbox externa manual", tornamos a sandbox um servico de primeira classe do compose.

## Decision

Execucao 100% containerizada via `docker compose`, em **duas zonas de rede**:

- **Zona app (confiavel)**: `gateway` (nginx), `frontend` (React/Vite), `backend` (FastAPI legado), `mcp-server`, `database` (PostgreSQL 18), `minio` (MinIO).
- **Zona sandbox (nao-confiavel)**: **uma unica** container `sandbox` onde o agente reside - roda `genie serve` (Claude Code), `omni` (Baileys) e `nats` internamente. Rede isolada.

Propriedade de seguranca central: a **unica** forma de o agente alcancar o negocio e o `mcp-server` (HTTP/SSE, com guardrails). O agente nao acessa Postgres nem MinIO direto. Mesmo sob prompt injection, so faz o que as tools permitem. O worker de notificacao fala com a sandbox (`omni`/`nats`) num caminho separado, so de saida.

`gateway` e o unico ponto exposto: `/` -> frontend, `/api` -> backend, `/mcp` -> mcp-server (SSE: `proxy_buffering off`, timeout alto), `/files/` -> bucket de faturas do MinIO (ver ADR-0009).

### Sandbox unica (decisao)

Optamos por **um** container `sandbox` (genie+omni+nats juntos) em vez de tres servicos separados. Trade-off: perde a separacao de processo entre canal e orquestracao (docs 04/05), mas e mais simples de blindar e de subir. A separacao logica e preservada dentro do container.

### Hardening (mitigacoes do doc 07 viram config)

- Least-privilege: so a credencial do Claude na sandbox - **ver ADR-0007** (auth do Claude Code reusada; **nao** uma `ANTHROPIC_API_KEY` dedicada obrigatoria). Sem SSH/AWS/GitHub/npm; fake no resto.
- Egress allowlist: WhatsApp + API Anthropic + `mcp`/`nats` internos.
- Imagens pinadas/verificadas: Genie/Omni em commit fixo (cosign/attestation do Genie), sem `curl|bash` em runtime, telemetria off (`OMNI_TELEMETRY=false`, `SENTRY_DSN=`).
- Container: non-root, `read_only` onde possivel, `cap_drop`, sem `docker.sock`, sem bind-mount sensivel do host.

### Rollout gradual

O compose cresce por incremento, cada um validado antes do proximo:

1. **`database` + `seed`** (este incremento).
2. `backend` + `mcp-server`.
3. `minio` (MinIO).
4. `frontend` + `gateway`.
5. `sandbox` (genie+omni+nats) + wiring.

## Consequences

Positivas:
- `docker compose up` reproduzivel para o avaliador; RNF de operabilidade atendida.
- Threat model do doc 07 vira artefato versionado (rede isolada, least-privilege, egress allowlist).
- Agente isolado atras do MCP reforca os guardrails (defense-in-depth).

Negativas:
- Construir a imagem Genie/Omni blindada e trabalhoso (nao e `up` trivial).
- Pareamento WhatsApp (QR) e interativo; documentado no runbook.
- Sandbox unica acopla canal+orquestracao no mesmo container.

## Alternatives

- **`genie`/`omni`/`nats` como servicos separados**: mais limpo (docs 04/05), porem mais peca para blindar; preterido a pedido (sandbox unica).
- **Sandbox externa nao-compose**: menos reproduzivel; perde o `up` unico.
- **Postgres `latest`**: nao reproduzivel; fixamos `postgres:18` (major estavel atual; 19 previsto set/2026).
