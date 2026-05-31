#!/usr/bin/env bash
# OPT-IN reverso (SPEC-019 / ADR-0010): desliga a rota direta de mídia e restaura o
# isolamento de rede default (egress-proxy = única rota de saída, doc 07/ADR-0006).
#
# Uso (no host):  bash sandbox/disable-media.sh
set -euo pipefail

SANDBOX="${SANDBOX_CONTAINER:-khal-sandbox}"
WANET="${MEDIA_NET:-bridge}"
log() { printf '\033[1;33m[disable-media]\033[0m %s\n' "$*"; }

command -v docker >/dev/null || { echo "docker CLI não encontrado (rode no host)"; exit 1; }
docker inspect "$SANDBOX" >/dev/null 2>&1 || { echo "container '$SANDBOX' não existe"; exit 1; }

# 1. Desconecta da rede com internet (idempotente).
if docker inspect "$SANDBOX" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -qw "$WANET"; then
  docker network disconnect "$WANET" "$SANDBOX"
  log "sandbox desconectado de '$WANET' (volta a só egress-proxy)"
else
  log "sandbox já não está em '$WANET' (ok)"
fi

# 2. Reinicia a API do Omni para reler o ambiente sem a rota direta.
#    Espera o GRACEFUL SHUTDOWN completar (pgserve parado, porta livre) antes do
#    novo boot; só força (-9) como fallback, limpando o postgres do pgserve do OMNI.
log "reiniciando a API do Omni…"
# Padrões via env var p/ pkill/pgrep não casarem o próprio shell (ver enable-media.sh).
docker exec -e API_PAT="packages/api/src/index.ts" -e PG_PAT="/srv/omni/.pgserve-data" \
  "$SANDBOX" sh -c '
  MARK=$(wc -l < /tmp/omni-api.log 2>/dev/null || echo 0)
  pkill -TERM -f "$API_PAT" 2>/dev/null || true
  for _ in $(seq 1 30); do
    tail -n +$((MARK+1)) /tmp/omni-api.log 2>/dev/null | grep -q "Graceful shutdown complete" && break
    pgrep -f "$API_PAT" >/dev/null || break
    sleep 1
  done
  pkill -9 -f "$API_PAT" 2>/dev/null || true
  pkill -9 -f "$PG_PAT" 2>/dev/null || true
  sleep 1' || true
docker exec -d "$SANDBOX" sh -c "cd /srv/omni && exec bun packages/api/src/index.ts >> /tmp/omni-api.log 2>&1"
log "isolamento de rede restaurado. A 2ª via volta a sair só pelo link (anexo best-effort)."
