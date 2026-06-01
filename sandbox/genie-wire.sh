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
# O bloco permissions.allow deste frontmatter é DERIVADO da fonte única
# src/interfaces/mcp/allowlist.py (permissions_allow()) e guardado no CI pelo
# teste tests/unit/test_tool_scope_parity.py. NÃO edite a allowlist à mão aqui
# no sandbox: ajuste a allowlist Python, regenere/valide e só então ele chega
# escopado. O sandbox não tem o src/ Python montado, por isso a paridade é
# garantida antes do build, não em runtime de wiring.
FRONTMATTER="${WIRE_FRONTMATTER:-/srv/agent/$AGENT_NAME.frontmatter.yaml}"
PERSONA_SRC="${WIRE_PERSONA:-/srv/agent-src/AGENTS.md}"   # bind-mount de implementation/agent
# CAG (R-08): diretorio da kb/ a pre-carregar no prefixo estavel do prompt.
# Best-effort: se o dir nao existir (mount ausente), o bloco KB e omitido e o
# agente cai no fallback `search_knowledge_base` — NAO quebra o wiring atual.
WIRE_KB="${WIRE_KB:-/srv/agent-src/kb}"
MCP_URL="${MCP_URL:-http://mcp-server:8000/mcp}"

# Monta o bloco KB ESTAVEL (mesma ordem por slug e formato de src/agent/prompt.py
# e infrastructure/knowledge.render_kb_block — paridade eval<->producao, M-07).
# Para cada verbete: cabecalho "### <slug> — <titulo>" + corpo (apos o 2o '---',
# com whitespace de borda removido, como o .strip() do Python). `sort` por path
# (prefixo comum) = ordem por slug -> prefixo byte-identico (cache, R-07).
build_kb_block() {
  local dir="$1" first=1 f slug titulo body
  [ -d "$dir" ] || return 0
  for f in $(find "$dir" -maxdepth 1 -name '*.md' | sort); do
    slug="$(basename "$f" .md)"
    titulo="$(sed -n 's/^titulo:[[:space:]]*//p' "$f" | head -n1)"
    # corpo = linhas apos a 2a ocorrencia de '---'; awk acumula em `b` e imprime
    # 1x no END, e o printf via "%s" (sem newline extra). O $(...) ja remove os
    # newlines finais; trim do inicio fica a cargo do bloco abaixo.
    body="$(awk '
      /^---/ { c++; next }
      c>=2  { b = b $0 "\n" }
      END   { printf "%s", b }
    ' "$f")"
    # trim de linhas em branco no inicio (equivale ao .strip() do render_kb_block).
    body="$(printf '%s' "$body" | sed -e '/./,$!d')"
    [ "$first" -eq 1 ] || printf '\n\n'
    first=0
    printf '### %s — %s\n%s' "$slug" "${titulo:-$slug}" "$body"
  done
}

# --- 1. Monta o AGENTS.md do agente (frontmatter + persona) -----------------
if [ ! -f "$PERSONA_SRC" ]; then
  log "AVISO: persona não encontrada em $PERSONA_SRC (bind-mount de implementation/agent ausente)."
  log "       Usando persona mínima de fallback (o E2E real precisa da persona da entrega)."
  PERSONA_BODY="# Agente de CX — Luz do Vale (fallback)\n\nMonte o bind-mount de implementation/agent para a persona real."
  PERSONA_SRC=""
fi
mkdir -p "$AGENT_DIR"
KB_BLOCK="$(build_kb_block "$WIRE_KB")"
{
  echo "---"
  cat "$FRONTMATTER"
  echo "---"
  echo
  # Prefixo ESTAVEL/cacheavel (R-07), na MESMA ordem de src/agent/prompt.py:
  #   1) persona (AGENTS.md)  2) bloco KB pre-carregado (CAG, R-08)
  # O sufixo VOLATIL (telefone do remetente) e injetado em RUNTIME pelo bridge,
  # nunca aqui — assim o prefixo permanece byte-identico entre conversas.
  if [ -n "$PERSONA_SRC" ]; then cat "$PERSONA_SRC"; else printf '%b\n' "$PERSONA_BODY"; fi
  if [ -n "$KB_BLOCK" ]; then
    printf '\n\n## Base de conhecimento (pré-carregada)\n%s\n' "$KB_BLOCK"
  fi
} > "$AGENT_DIR/AGENTS.md"
if [ -n "$KB_BLOCK" ]; then
  log "agente montado: $AGENT_DIR/AGENTS.md (frontmatter + persona + KB CAG de $WIRE_KB)"
else
  log "agente montado: $AGENT_DIR/AGENTS.md (frontmatter + persona; KB CAG ausente em $WIRE_KB — fallback search_knowledge_base)"
fi

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

# --- 2b. Hooks de guardrail do Claude Code (R-20, escopo user) --------------
# Copia o settings.json (registro dos hooks PreToolUse/UserPromptSubmit) para o
# escopo USER do Claude Code (~/.claude/settings.json), persistido no volume
# claude-home. O script guardrail.py é alcançado em /srv/agent/hooks (bind-mount
# read-only, ver compose.sandbox.yml). Idempotente e REVERSÍVEL: sem o arquivo de
# origem (ou removendo ~/.claude/settings.json) os hooks ficam desligados, sem
# afetar tool-scoping/rede-só-MCP/validação no MCP.
HOOKS_SETTINGS="${WIRE_HOOKS_SETTINGS:-/srv/agent/settings.json}"
CLAUDE_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
if [ -f "$HOOKS_SETTINGS" ]; then
  if command -v python3 >/dev/null 2>&1 && ! python3 -c "import json,sys; json.load(open('$HOOKS_SETTINGS'))" 2>/dev/null; then
    log "AVISO: settings.json inválido ($HOOKS_SETTINGS) — hooks NÃO registrados."
  else
    mkdir -p "$CLAUDE_HOME"
    cp "$HOOKS_SETTINGS" "$CLAUDE_HOME/settings.json"
    log "hooks de guardrail registrados: $CLAUDE_HOME/settings.json"
  fi
else
  log "nota: $HOOKS_SETTINGS ausente — hooks de guardrail (R-20) não registrados."
fi

# --- 3. Sincroniza o diretório de agentes do Genie (se serve já estiver up) --
if [ "${WIRE_SYNC:-0}" = "1" ]; then
  ( cd "$WS" && genie agents sync >/dev/null 2>&1 && log "agent-sync executado" ) || \
    log "nota: agent-sync será feito pelo genie serve no startup"
fi

log "wiring concluído. agente=$AGENT_NAME provider=claude (tmux/CLI) tools=mcp__luz-do-vale__* (só)"
