#!/usr/bin/env bash
# Orquestracao dos processos do sandbox (Genie + Omni), rodando como `node`.
# Ordem: postgres-do-genie -> NATS -> postgres+API do Omni -> genie init -> genie serve.
#
# Premissas (doc 07 / ADR-0006):
#   - SEM curl|bash, SEM instaladores globais; todos os binarios ja vem na imagem.
#   - Genie em modo force-TCP num postgres DEDICADO (isolado do banco do Omni).
#   - Telemetria off; rede so alcanca o mcp-server (negocio) + egress allowlist.
#
# Uso (dentro do container):  bash /srv/sandbox-up.sh
set -euo pipefail

log() { printf '\033[1;36m[sandbox-up]\033[0m %s\n' "$*"; }

# --- Resolve a plataforma do embedded-postgres (mesmo PK do Dockerfile) ---
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in
  amd64|x86_64) PK=linux-x64 ;;
  arm64|aarch64) PK=linux-arm64 ;;
  *) PK="linux-$ARCH" ;;
esac
PG_ROOT="$HOME/.pgserve/bin/$PK"
PGBIN="$PG_ROOT/bin"
export LD_LIBRARY_PATH="$PG_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

GENIE_PGDATA="$HOME/.genie/pgdata"
GENIE_PG_PORT="${GENIE_PG_PORT:-19642}"

pg_ready() { grep -q "ready to accept connections" "$1" 2>/dev/null; }
wait_log() { local f="$1" pat="$2" n="${3:-60}"; for _ in $(seq 1 "$n"); do grep -q "$pat" "$f" 2>/dev/null && return 0; sleep 0.25; done; return 1; }

# ---------------------------------------------------------------------------
# 1. Postgres dedicado do Genie (force-TCP em 127.0.0.1:$GENIE_PG_PORT)
# ---------------------------------------------------------------------------
if [ ! -s "$GENIE_PGDATA/PG_VERSION" ]; then
  log "initdb do postgres do genie em $GENIE_PGDATA"
  "$PGBIN/initdb" -D "$GENIE_PGDATA" -U postgres --auth=trust -E UTF8 >/tmp/genie-initdb.log 2>&1
fi
log "subindo postgres do genie :$GENIE_PG_PORT"
"$PGBIN/postgres" -D "$GENIE_PGDATA" -p "$GENIE_PG_PORT" -k /tmp -c listen_addresses=127.0.0.1 >/tmp/genie-pg.log 2>&1 &
wait_log /tmp/genie-pg.log "ready to accept" || { log "FALHA: postgres do genie"; tail -20 /tmp/genie-pg.log; exit 1; }
log "postgres do genie UP"

# Genie NAO auto-cria o DB em force-TCP -> garante o database `genie`.
# Roda de /srv/genie (onde o pacote `postgres` resolve).
( cd /srv/genie && bun -e 'import pg from "postgres"; const s=pg({host:"127.0.0.1",port:Number(process.env.GENIE_PG_PORT||19642),database:"postgres",username:"postgres",password:"postgres"}); const r=await s`select 1 from pg_database where datname=${"genie"}`; if(r.length===0){await s.unsafe("CREATE DATABASE genie"); console.log("[sandbox-up] DB genie criado");} await s.end()' )

# ---------------------------------------------------------------------------
# 2. NATS (event bus do Omni; o omni-bridge do genie assina aqui)
# ---------------------------------------------------------------------------
log "subindo nats-server :4222 (com JetStream)"
# JetStream (-js) é exigido pela Omni API (event bus); sem ele a API loga
# "running without event bus". -sd fixa o store dir em local node-writable.
mkdir -p "$HOME/.nats-js"
nats-server -p 4222 -js -sd "$HOME/.nats-js" >/tmp/nats.log 2>&1 &
wait_log /tmp/nats.log "Server is ready" 40 || log "aviso: nats sem 'Server is ready' (segue)"

# ---------------------------------------------------------------------------
# 3. Omni: pgserve embutido + API REST (:8882). Usa /srv/omni/.env da imagem.
# ---------------------------------------------------------------------------
log "subindo Omni API :8882 (pgserve embutido + migrations)"
( cd /srv/omni && bun packages/api/src/index.ts >/tmp/omni-api.log 2>&1 & )
wait_log /tmp/omni-api.log "listening\|started\|ready\|8882" 120 || log "aviso: omni API sem marcador claro (cheque /tmp/omni-api.log)"

# ---------------------------------------------------------------------------
# 4. Genie: workspace + agente + serve headless (force-TCP no postgres do genie)
# ---------------------------------------------------------------------------
export GENIE_PG_FORCE_TCP=1 GENIE_PG_PORT="$GENIE_PG_PORT" GENIE_DB_NAME=genie PGPASSWORD=postgres
if [ ! -d /srv/omni/.genie/agents ] && [ ! -d /srv/omni/agents/genie ]; then
  log "genie init (workspace + agente default)"
  ( cd /srv/omni && printf 'y\n' | genie init >/tmp/genie-init.log 2>&1 ) || { log "FALHA genie init"; tail -20 /tmp/genie-init.log; exit 1; }
fi

# Wiring do agente CX `luz-do-vale` (tool-scoping + MCP) ANTES do serve, p/ o
# agent-sync do serve já registrar o agente escopado.
if [ -x /srv/genie-wire.sh ]; then
  log "wiring do agente CX (genie-wire.sh)"
  bash /srv/genie-wire.sh || log "aviso: genie-wire.sh retornou erro (segue)"
fi

log "genie serve start --headless"
# NOTA (corrida no spawn a frio): a PRIMEIRA omni.message de um chat cria a sessão
# tmux do agente, mas pode não entrar na TUI a tempo (a entrega corre com o
# bootstrap do Claude Code). A SEGUNDA mensagem (sessão já ativa) entra via
# deliver() e roda normal. Mitigação no E2E/demo: reenviar a 1ª mensagem, ou
# mandar um "oi" de aquecimento antes da mensagem real. Ver poc/sandbox/RUNBOOK.md.
cd /srv/omni
exec genie serve start --headless --no-interactive --no-tui
