# Imagem do sandbox (Genie + Omni + NATS), a partir dos clones PINADOS de libs/.
# Postura doc 07: build isolado, sem instaladores globais (curl|bash / bun add -g),
# telemetria off, non-root.
# Contexto de build = raiz do repo de entrega (implementation/).
#   docker build -f sandbox/Dockerfile -t khal-sandbox:base .
#   (clones pinados em sandbox/libs/{genie,omni}, gitignored - ver sandbox/README.md)
#
# Fase atual: toolchain + Genie + Omni (instalados dos clones).

FROM node:20-bookworm-slim AS base

ENV DEBIAN_FRONTEND=noninteractive \
    CI=true \
    HUSKY=0 \
    OMNI_TELEMETRY=false \
    SENTRY_DSN=""

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux git ca-certificates curl procps libicu72 \
    && rm -rf /var/lib/apt/lists/*

# Usa o usuario non-root `node` (uid 1000, ja presente na imagem). postgres/initdb
# recusam root; non-root e tambem o hardening do ADR-0006.

# NATS server embutido (pinado). O Omni baixaria do GitHub em runtime, mas o
# egress allowlist (so Anthropic+WhatsApp) bloquearia -> obtemos no build.
ARG NATS_VERSION=v2.12.4
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) NA=amd64;; arm64) NA=arm64;; *) NA=$ARCH;; esac \
    && curl -fsSL "https://github.com/nats-io/nats-server/releases/download/${NATS_VERSION}/nats-server-${NATS_VERSION}-linux-${NA}.tar.gz" -o /tmp/nats.tgz \
    && tar -xzf /tmp/nats.tgz -C /tmp \
    && cp "/tmp/nats-server-${NATS_VERSION}-linux-${NA}/nats-server" /usr/local/bin/ \
    && rm -rf /tmp/nats* \
    && nats-server --version

# Binarios do Postgres embutido (pgserve). Em runtime ele baixaria
# @embedded-postgres do npm -> bloqueado pelo egress allowlist; pre-popula o
# cache ~/.pgserve/bin/<platformKey> no build (com internet).
ARG EMBEDDED_PG_VERSION=18.2.0-beta.16
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) PK=linux-x64;; arm64) PK=linux-arm64;; *) PK=linux-$ARCH;; esac \
    && curl -fsSL "https://registry.npmjs.org/@embedded-postgres/${PK}/-/${PK}-${EMBEDDED_PG_VERSION}.tgz" -o /tmp/ep.tgz \
    && mkdir -p /tmp/ep "/home/node/.pgserve/bin/${PK}" \
    && tar -xzf /tmp/ep.tgz -C /tmp/ep \
    && cp -a /tmp/ep/package/native/. "/home/node/.pgserve/bin/${PK}/" \
    && rm -rf /tmp/ep* \
    && chown -R node:node /home/node/.pgserve \
    && ls "/home/node/.pgserve/bin/${PK}/bin/postgres" "/home/node/.pgserve/bin/${PK}/bin/initdb" \
    # Symlinks de soname (libpq.so.5.18 -> libpq.so.5, libicuuc.so.60.2 -> .60, ...).
    # Sem eles, initdb/postgres falham com "cannot open shared object file".
    && for f in "/home/node/.pgserve/bin/${PK}/lib/"*.so.*; do \
         base=$(echo "$f" | sed -E 's/(\.so\.[0-9]+)\.[0-9]+$/\1/'); \
         [ "$f" != "$base" ] && [ ! -e "$base" ] && ln -s "$(basename "$f")" "$base" || true; \
       done
# NOTA: NAO setar LD_LIBRARY_PATH como ENV global — o embedded-postgres traz um
# liblzma.so.5 antigo (sem XZ_5.4) que quebra apt/dpkg em layers seguintes.
# O sandbox-up.sh exporta LD_LIBRARY_PATH apenas em runtime (escopo dos daemons pg).

# bun pinado via npm (sem curl|bash). Genie exige bun >= 1.3.10.
RUN npm install -g bun@1.3 && bun --version

# Claude Code (instalacao fresh; login manual persiste em volume - ADR-0007).
# O Genie (executor tmux) spawna este binario para rodar o agente.
RUN npm install -g @anthropic-ai/claude-code && claude --version

WORKDIR /srv

# --- Genie (clone pinado libs/genie@a407a2e2) ---
COPY sandbox/libs/genie ./genie
WORKDIR /srv/genie
# Instala deps sem lifecycle scripts (postinstall baixa tmux/builda hook/migrations;
# tmux ja vem do apt). Roda o build do binario.
RUN bun install --ignore-scripts
RUN bun run build && ls -la dist/genie.js

# --- Omni (clone pinado libs/omni@fe155b81) ---
WORKDIR /srv
COPY sandbox/libs/omni ./omni
WORKDIR /srv/omni
ENV OMNI_PACKAGES_DIR=/srv/omni/packages
RUN bun install --ignore-scripts
# @omni/sdk e usado pelo CLI/API e precisa do dist (equivale ao _build-dist do Makefile).
RUN cd packages/sdk && bun run build
# Symlinks de ICU para o postgres embutido (era o postinstall pulado).
RUN node scripts/ensure-libicu-symlinks.cjs || true
# Smoke do CLI (a partir do clone).
RUN bun packages/cli/src/index.ts --version 2>&1 | head -3

# Config de runtime do Omni (sandbox isolada; key de dev, telemetria off).
RUN cat > /srv/omni/.env <<'EOF'
DATABASE_URL=postgresql://postgres:postgres@localhost:8432/omni
PGSERVE_EMBEDDED=true
PGSERVE_PORT=8432
PGSERVE_DATA=/srv/omni/.pgserve-data
NATS_URL=nats://localhost:4222
NATS_MANAGED=true
NATS_PORT=4222
NODE_ENV=development
LOG_LEVEL=info
API_PORT=8882
API_HOST=0.0.0.0
API_MANAGED=true
OMNI_API_KEY=sandbox-dev-key
OMNI_TELEMETRY=false
SENTRY_DSN=
OMNI_PACKAGES_DIR=/srv/omni/packages
EOF

# Genie: jq + wrapper `genie` no PATH (ele faz shell-out de `genie`).
RUN apt-get update && apt-get install -y --no-install-recommends jq && rm -rf /var/lib/apt/lists/*
RUN printf '#!/bin/sh\nexec bun /srv/genie/dist/genie.js "$@"\n' > /usr/local/bin/genie \
    && chmod +x /usr/local/bin/genie
# Wrapper `omni` no PATH: o agente CX responde o WhatsApp via `omni say`/`omni done`
# (verbos shell escopados por `Bash(omni:*)` no frontmatter). Fala com a API local.
RUN printf '#!/bin/sh\ncd /srv/omni\nexec bun /srv/omni/packages/cli/src/index.ts "$@"\n' > /usr/local/bin/omni \
    && chmod +x /usr/local/bin/omni

# Marca o setup do Genie como concluido -> `genie init/serve` nao dispara o
# wizard interativo (isSetupComplete() le ~/.genie/config.json.setupComplete).
RUN mkdir -p /home/node/.genie \
    && printf '{"setupComplete": true}\n' > /home/node/.genie/config.json

# Cria ~/.claude no build (node-owned) p/ o volume `claude-home` HERDAR a dono
# node ao ser criado (login do Claude Code grava credenciais aqui — ADR-0007).
# Sem isto o volume nasce root-owned e o `claude login` (non-root) falha.
RUN mkdir -p /home/node/.claude

# Script de orquestracao dos processos (postgres-genie + NATS + Omni + genie serve).
COPY --chmod=0755 sandbox/sandbox-up.sh /srv/sandbox-up.sh
# Wiring do agente CX `luz-do-vale`: tool-scoping (frontmatter) + MCP.
COPY --chmod=0755 sandbox/genie-wire.sh /srv/genie-wire.sh
COPY sandbox/agent/luz-do-vale.frontmatter.yaml /srv/agent/luz-do-vale.frontmatter.yaml

# Runtime non-root: o sandbox e dono do codigo e do home (claude/genie/omni state).
RUN chown -R node:node /srv/omni /srv/genie /home/node
ENV HOME=/home/node
USER node
WORKDIR /srv/omni
