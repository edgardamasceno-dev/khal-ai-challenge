#!/usr/bin/env bash
# OPT-IN (SPEC-019 / ADR-0010): habilita o upload de anexo de mídia (2ª via PDF) no
# WhatsApp. Roda NO HOST (precisa do docker CLI), fora do sandbox.
#
# Por quê: o upload do Baileys aos CDNs de mídia (mmg/*.cdn.whatsapp.net) usa
# `fetch` com streaming, que o Bun NÃO tuneliza através do proxy HTTP CONNECT do
# egress (tinyproxy). Sem o proxy no caminho, o upload sobe (confirmado: 200/201).
# O `NO_PROXY` do sandbox já lista os CDNs (compose.sandbox.yml) — aqui só damos a
# rota direta (NAT) para esses hosts saírem sem o proxy.
#
# Trade-off (ADR-0010): isto conecta o sandbox a uma rede com saída de internet.
# O default da entrega é ISOLADO (egress-proxy = única rota); este script é opt-in,
# reversível por `disable-media.sh`, e deve ser usado só em demo controlada.
#
# Uso (no host):  bash sandbox/enable-media.sh
set -euo pipefail

SANDBOX="${SANDBOX_CONTAINER:-khal-sandbox}"
WANET="${MEDIA_NET:-bridge}"   # rede com saída NAT; default = bridge do Docker
CDNS="mmg.whatsapp.net,.cdn.whatsapp.net,.fna.whatsapp.net"
log() { printf '\033[1;33m[enable-media]\033[0m %s\n' "$*"; }

command -v docker >/dev/null || { echo "docker CLI não encontrado (rode no host)"; exit 1; }
docker inspect "$SANDBOX" >/dev/null 2>&1 || { echo "container '$SANDBOX' não existe"; exit 1; }

# 1. Conecta o sandbox à rede com internet (idempotente).
if docker inspect "$SANDBOX" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -qw "$WANET"; then
  log "sandbox já está na rede '$WANET' (ok)"
else
  docker network connect "$WANET" "$SANDBOX"
  log "sandbox conectado à rede '$WANET' (saída direta p/ CDNs de mídia)"
fi

# 2. Garante que a API do Omni roda com NO_PROXY incluindo os CDNs.
#    - Se o Omni já está rodando com o NO_PROXY certo (sandbox criado pelo compose
#      atualizado), NÃO reinicia (evita o restart do pgserve embutido, que é delicado).
#    - Senão, reinicia com NO_PROXY explícito, esperando o GRACEFUL SHUTDOWN completar
#      (libera o pgserve/porta) antes do novo boot.
RUNNING_NP="$(docker exec "$SANDBOX" sh -c "tr '\0' '\n' < /proc/\$(pgrep -f 'packages/api/src/index.ts' | head -1)/environ 2>/dev/null | sed -n 's/^NO_PROXY=//p'" 2>/dev/null || true)"
if printf '%s' "$RUNNING_NP" | grep -q "mmg.whatsapp.net"; then
  log "Omni já roda com NO_PROXY nos CDNs — sem restart. Anexo de mídia HABILITADO. ✅"
  log "Teste: POST /invoices/{id}/send do titular real -> enviado_anexo: true."
  exit 0
else
  BASE_NP="$(docker exec "$SANDBOX" printenv NO_PROXY 2>/dev/null || echo 'mcp-server,localhost,127.0.0.1')"
  case ",$BASE_NP," in *",mmg.whatsapp.net,"*) NP="$BASE_NP" ;; *) NP="$BASE_NP,$CDNS" ;; esac
  log "reiniciando a API do Omni (NO_PROXY=$NP)…"
  BOOT_MARK="$(docker exec "$SANDBOX" sh -c 'wc -l < /tmp/omni-api.log 2>/dev/null || echo 0')"
  # SIGTERM e ESPERA o "Graceful shutdown complete" (garante pgserve parado + porta
  # livre). Só força (-9) como fallback, e aí limpa o postgres do pgserve do OMNI
  # (data dir /srv/omni/.pgserve-data) — nunca o do Genie (~/.genie/pgdata).
  # Os padrões vão por env var: a cmdline do `sh -c` mostra "$API_PAT" literal (não
  # o valor), então pkill/pgrep não casam o próprio shell que os executa (senão
  # `pkill -f` se auto-mataria → SIGTERM → set -e abortaria antes do boot).
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
  docker exec -d -e NO_PROXY="$NP" -e no_proxy="$NP" "$SANDBOX" \
    sh -c "cd /srv/omni && exec bun packages/api/src/index.ts >> /tmp/omni-api.log 2>&1"

  # 3. Aguarda reconectar — só conta "Instance connected" logado APÓS o boot (marca).
  log "aguardando a API do Omni reconectar…"
  for _ in $(seq 1 24); do
    if docker exec "$SANDBOX" sh -c "
      pgrep -f 'packages/api/src/index.ts' >/dev/null \
      && tail -n +$((BOOT_MARK+1)) /tmp/omni-api.log 2>/dev/null | grep -q 'Instance connected'"; then
      log "Omni reconectado. Anexo de mídia HABILITADO. ✅"
      log "Teste: POST /invoices/{id}/send do titular real -> enviado_anexo: true."
      exit 0
    fi
    sleep 2
  done
  log "aviso: não vi 'Instance connected' a tempo; cheque /tmp/omni-api.log."
fi
