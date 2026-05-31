#!/usr/bin/env bash
# Wiring do agente CX `luz-do-vale` no Genie + tool-scoping + MCP.
# Idempotente. Roda como `node`, dentro do sandbox, ANTES (ou junto) do genie serve.
#
# O que faz:
#   1. Monta agents/luz-do-vale/AGENTS.md = frontmatter (tool-scoping) + persona da
#      entrega (implementation/agent/AGENTS.md, bind-mounted em /srv/agent-src).
#   2. Registra o MCP `luz-do-vale` no Claude Code em escopo USER (persiste no
#      volume claude-home) -> o Claude spawnado pelo Genie enxerga mcp__luz-do-vale__*.
#   3. (opcional) Sincroniza o diretório de agentes do Genie agora.
#
# Camadas de guardrail (doc 09): tool-scoping forte (allow só MCP, deny WebFetch/
# WebSearch/Bash/escrita) + rede só-MCP + egress allowlist.
set -euo pipefail
log() { printf '\033[1;35m[genie-wire]\033[0m %s\n' "$*"; }

WS="${GENIE_WORKSPACE:-/srv/omni}"
AGENT_NAME=luz-do-vale
AGENT_DIR="$WS/agents/$AGENT_NAME"
FRONTMATTER="${WIRE_FRONTMATTER:-/srv/agent/$AGENT_NAME.frontmatter.yaml}"
PERSONA_SRC="${WIRE_PERSONA:-/srv/agent-src/AGENTS.md}"   # bind-mount de implementation/agent
MCP_URL="${MCP_URL:-http://mcp-server:8000/mcp}"

# --- 1. Monta o AGENTS.md do agente (frontmatter + persona) -----------------
if [ ! -f "$PERSONA_SRC" ]; then
  log "AVISO: persona não encontrada em $PERSONA_SRC (bind-mount de implementation/agent ausente)."
  log "       Usando persona mínima de fallback (o E2E real precisa da persona da entrega)."
  PERSONA_BODY="# Agente de CX — Luz do Vale (fallback)\n\nMonte o bind-mount de implementation/agent para a persona real."
  PERSONA_SRC=""
fi
mkdir -p "$AGENT_DIR"
{
  echo "---"
  cat "$FRONTMATTER"
  echo "---"
  echo
  if [ -n "$PERSONA_SRC" ]; then cat "$PERSONA_SRC"; else printf '%b\n' "$PERSONA_BODY"; fi
} > "$AGENT_DIR/AGENTS.md"
log "agente montado: $AGENT_DIR/AGENTS.md (frontmatter + persona)"

# --- 2. Registra o MCP no Claude Code (escopo user, persiste no volume) ------
# `claude mcp add` é idempotente o suficiente: removemos antes p/ refletir mudanças de URL.
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user "$AGENT_NAME" >/dev/null 2>&1 || true
  if claude mcp add --transport http --scope user "$AGENT_NAME" "$MCP_URL" >/dev/null 2>&1; then
    log "MCP registrado (user): $AGENT_NAME -> $MCP_URL"
  else
    log "AVISO: 'claude mcp add' falhou (claude logado? versão?). Configure o MCP manualmente."
  fi
  claude mcp list 2>/dev/null | sed 's/^/  /' || true
else
  log "AVISO: binário 'claude' ausente — pulei o registro do MCP."
fi

# --- 3. Sincroniza o diretório de agentes do Genie (se serve já estiver up) --
if [ "${WIRE_SYNC:-0}" = "1" ]; then
  ( cd "$WS" && genie agents sync >/dev/null 2>&1 && log "agent-sync executado" ) || \
    log "nota: agent-sync será feito pelo genie serve no startup"
fi

log "wiring concluído. agente=$AGENT_NAME provider=claude (tmux/CLI) tools=mcp__luz-do-vale__* (só)"
