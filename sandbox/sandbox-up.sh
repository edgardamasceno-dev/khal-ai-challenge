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

# R-05 (cold-start estrutural): GENIE_PGDATA é configurável por env para poder
# apontar a um VOLUME NOMEADO (compose.sandbox.yml) e sobreviver a
# `--force-recreate`. Default = caminho legado no FS do container (reversível:
# sem o volume, o comportamento é exatamente o de antes). Fica FORA de
# `~/.genie` de propósito, p/ não cobrir o config.json (setupComplete) do build.
GENIE_PGDATA="${GENIE_PGDATA:-$HOME/.genie/pgdata}"
GENIE_PG_PORT="${GENIE_PG_PORT:-19642}"

pg_ready() { grep -q "ready to accept connections" "$1" 2>/dev/null; }
wait_log() { local f="$1" pat="$2" n="${3:-60}"; for _ in $(seq 1 "$n"); do grep -q "$pat" "$f" 2>/dev/null && return 0; sleep 0.25; done; return 1; }

# ---------------------------------------------------------------------------
# 0. R-05: garante que $GENIE_PGDATA é gravável pelo `node` (non-root).
# ---------------------------------------------------------------------------
# Um volume nomeado montado num path que NÃO existia na imagem nasce root-owned,
# e o `initdb` (non-root) falharia. Em vez de quebrar o sandbox que já funciona,
# fazemos FALLBACK reversível para o path legado efêmero, com aviso. Quando o
# mountpoint é node-gravável (volume herdou dono node, p.ex. dir pré-criado no
# Dockerfile), a persistência entre `--force-recreate` fica ativa.
mkdir -p "$GENIE_PGDATA" 2>/dev/null || true
if [ ! -w "$GENIE_PGDATA" ]; then
  log "AVISO: $GENIE_PGDATA não é gravável (volume root-owned?); usando FS efêmero."
  log "       p/ persistir o cold-start, garanta o dir node-owned (ver RUNBOOK R-05)."
  GENIE_PGDATA="$HOME/.genie/pgdata"
  mkdir -p "$GENIE_PGDATA"
fi
log "GENIE_PGDATA=$GENIE_PGDATA"

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

# ---------------------------------------------------------------------------
# 5. R-05: WARM-POOL determinístico (opt-in) — aquece o pane de cada persona-âncora
# ---------------------------------------------------------------------------
# A corrida no spawn a frio (NOTA abaixo) some quando a sessão já está quente. O
# warm-pool publica 1 `omni.message` SINTÉTICA de aquecimento por telefone-âncora
# DEPOIS que o serve sobe, forçando spawn+resume — o 1º turno REAL do cliente cai
# numa sessão já ativa (sem perder o 1º "oi" na corrida do bootstrap). Casado com
# o `--resume` do Genie + pgdata persistente (R-05), o cold-start é pago uma vez.
#
# REVERSÍVEL/opt-in: $WARM_POOL_PHONES vazio (default) = warm-pool DESLIGADO,
# comportamento idêntico ao de antes. Formato: telefones separados por espaço/vírgula
# (use as personas-âncora do .env, ex.: "555199990001 555199990002").
WARM_POOL_PHONES="${WARM_POOL_PHONES:-}"
WARM_POOL_DELAY="${WARM_POOL_DELAY:-8}"
WARM_POOL_MSG="${WARM_POOL_MSG:-oi}"
if [ -n "$WARM_POOL_PHONES" ]; then
  log "warm-pool agendado p/ [$WARM_POOL_PHONES] (delay ${WARM_POOL_DELAY}s)"
  (
    sleep "$WARM_POOL_DELAY"
    for ph in $(printf '%s' "$WARM_POOL_PHONES" | tr ',' ' '); do
      [ -n "$ph" ] || continue
      ( cd /srv/genie && WARM_PH="$ph" WARM_MSG="$WARM_POOL_MSG" bun -e '
        import { connect, StringCodec } from "nats";
        const sc = StringCodec();
        const nc = await connect({ servers: "localhost:4222" });
        const ph = process.env.WARM_PH;
        nc.publish(`omni.message.warmpool.${ph}`, sc.encode(JSON.stringify({
          content: process.env.WARM_MSG, sender: ph, chatId: ph,
          instanceId: "warmpool", agent: "luz-do-vale"
        })));
        await nc.drain();
      ' >/tmp/warmpool.log 2>&1 ) && log "warm-pool: aquecido $ph" || log "warm-pool: falha $ph (segue)"
    done
  ) &
fi

# ---------------------------------------------------------------------------
# 5b. Claude Code: garante o onboarding marcado (idempotente, sobrevive a recreate)
# ---------------------------------------------------------------------------
# O token do `claude login` persiste no volume claude-home (~/.claude/.credentials.json),
# mas o ESTADO DE ONBOARDING vive em ~/.claude.json (arquivo IRMÃO, FORA do volume) e é
# RESETADO a cada `--force-recreate` -> o spawn TUI do agente (Genie) cai na tela "Select
# login method" mesmo com credencial válida (o `claude -p` headless já funciona). Aqui, se
# houver credencial, garantimos hasCompletedOnboarding=true (+ theme) ANTES do serve, p/ o
# spawn não parar no onboarding. Só toca essas flags; NÃO mexe na credencial. Sem credencial
# não faz nada (o operador ainda precisa do `claude login` — RUNBOOK Etapa 2). Análogo ao
# setupComplete do Genie semeado no Dockerfile; aqui é em runtime por ~/.claude.json ser efêmero.
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
if [ -f "$CLAUDE_HOME/.credentials.json" ] && command -v node >/dev/null 2>&1; then
  node -e '
    const fs=require("fs"),os=require("os"),p=os.homedir()+"/.claude.json";
    let d={}; try { d=JSON.parse(fs.readFileSync(p,"utf8")); } catch(_) {}
    let changed=false;
    if (d.hasCompletedOnboarding!==true){ d.hasCompletedOnboarding=true; changed=true; }
    if (!d.theme){ d.theme="dark"; changed=true; }
    // Pre-aceita o "trust dialog" (Is this a project you trust?) das pastas do agente
    // (SPEC-030): o spawn do Genie roda em /srv/omni/agents/luz-do-vale e, num ~/.claude.json
    // resetado pelo recreate, o 1o turno TRAVA na pergunta de trust (nao ha humano p/ responder).
    d.projects = d.projects || {};
    for (const dir of ["/srv/omni","/srv/omni/agents/luz-do-vale"]) {
      const pr = d.projects[dir] = d.projects[dir] || {};
      if (pr.hasTrustDialogAccepted!==true){ pr.hasTrustDialogAccepted=true; changed=true; }
    }
    if (changed) fs.writeFileSync(p, JSON.stringify(d));
    process.stdout.write("onboarding="+d.hasCompletedOnboarding+" trust="+Object.keys(d.projects).length+"dirs"+(changed?" (ajustado)":" (ja ok)"));
  ' 2>/dev/null | sed 's/^/[sandbox-up] claude onboarding+trust: /'; echo
else
  log "claude: sem credencial em $CLAUDE_HOME — faça claude login (RUNBOOK Etapa 2); onboarding não tocado"
fi

log "genie serve start --headless"
# NOTA (corrida no spawn a frio): a PRIMEIRA omni.message de um chat cria a sessão
# tmux do agente, mas pode não entrar na TUI a tempo (a entrega corre com o
# bootstrap do Claude Code). A SEGUNDA mensagem (sessão já ativa) entra via
# deliver() e roda normal. Mitigação no E2E/demo: reenviar a 1ª mensagem, mandar
# um "oi" de aquecimento, ou habilitar o WARM-POOL acima ($WARM_POOL_PHONES).
# Ver sandbox/RUNBOOK.md §7 (R-05).
#
# NOTA (heartbeat anti-nudge): turnos longos (PDF/multi-tool) não podem morrer no
# nudge de 120s. O `genie serve` emite o `agent-heartbeat` (~30s) que mantém o
# pane vivo; validar ao vivo nos logs do serve (ver RUNBOOK §7).
#
# NOTA (invalidação de sessão por hash, R-05): o `--resume` reanexa o pane do
# chat; se a persona/tool-set mudou, a sessão antiga tem prompt obsoleto. O
# fingerprint determinístico (`src/agent/session_hash.py::session_fingerprint`)
# é a base p/ invalidar (clear-session) quando o hash diverge — função PURA
# testada offline; o disparo aqui é CONFIG + validação ao vivo (o sandbox não
# monta `src/` Python). Ver RUNBOOK §7.
cd /srv/omni
exec genie serve start --headless --no-interactive --no-tui
