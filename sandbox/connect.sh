#!/usr/bin/env bash
# make sandbox-connect — Etapa 6.3 do RUNBOOK (determinístico). Liga a instância
# pareada (luzdovale-bot) ao agente CX `luz-do-vale` via `omni connect`, com as envs
# force-TCP do postgres do genie (o omni descobre o agente no diretório do genie).
# Pré-req: make sandbox-pair + você pareou o código no celular do bot (status=connected).
set -euo pipefail

SB=khal-sandbox
INST=luzdovale-bot
AGENT=luz-do-vale

om() { docker exec "$SB" sh -c "cd /srv/omni && $*"; }

ID=$(om "omni instances list 2>/dev/null" | awk -v n="$INST" '$2==n {print $1}' | head -1)
[ -n "$ID" ] || { echo "instância '$INST' não existe — rode: make sandbox-pair PHONE=+<DDI><numero>" >&2; exit 1; }

st=$(om "omni instances status $ID 2>/dev/null" | awk '/^state/{print $2}')
echo ">> instância $ID — estado=$st"
[ "$st" = "connected" ] || echo ">> AVISO: não está 'connected'. Pareou o código no celular do bot? (make sandbox-pair)"

docker exec "$SB" sh -c "cd /srv/omni && \
  GENIE_PG_FORCE_TCP=1 GENIE_PG_PORT=19642 GENIE_DB_NAME=genie PGPASSWORD=postgres \
  omni connect $ID $AGENT" 2>&1 | tail -4

cat <<EOF
>> instância ligada ao agente '$AGENT'.
   Agora mande UMA mensagem do celular CLIENTE (ex.: "oi") para o bot e rode:
     make sandbox-reseed        (auto-detecta o seu LID e re-chaveia a persona)
EOF
