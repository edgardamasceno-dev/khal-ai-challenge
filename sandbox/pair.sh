#!/usr/bin/env bash
# make sandbox-pair PHONE=+<DDI><numero> — Etapas 6.1+6.2 do RUNBOOK (determinístico).
#
# Faz a cola CLI do pareamento do WhatsApp: omni auth (key efêmera do log) + cria/reusa
# a instância `luzdovale-bot` + conecta o Baileys + gera o PAIRING CODE p/ o número do bot.
# A ÚNICA ação física sua é digitar o código no celular do bot. Idempotente (reusa a
# instância existente). Pré-req: make sandbox-serve (Omni API no ar).
set -euo pipefail

SB=khal-sandbox
INST=luzdovale-bot
PHONE="${1:-}"

[ -n "$PHONE" ] || { echo "uso: make sandbox-pair PHONE=+<DDI><numero-do-bot>   (ex.: PHONE=+16472015092)" >&2; exit 1; }
case "$PHONE" in +[0-9]*) ;; *) echo "PHONE deve começar com + e DDI (ex.: +16472015092)" >&2; exit 1;; esac

om() { docker exec "$SB" sh -c "cd /srv/omni && $*"; }

# 1. omni auth — a key é efêmera (pgserve do omni reinicia a cada serve); pega do log.
KEY=$(docker exec "$SB" sh -lc 'grep -ohE "omni_sk_[A-Za-z0-9]+" /tmp/omni-api.log /tmp/up.log 2>/dev/null | head -1')
[ -n "$KEY" ] || { echo "não achei 'omni_sk_' no log do Omni — o Omni API subiu? (make sandbox-serve)" >&2; exit 1; }
om "omni auth login --api-key $KEY" >/dev/null 2>&1 && echo ">> omni auth OK"

# 2. cria ou reusa a instância luzdovale-bot.
ID=$(om "omni instances list 2>/dev/null" | awk -v n="$INST" '$2==n {print $1}' | head -1)
if [ -z "$ID" ]; then
  ID=$(om "omni instances create --name $INST --channel whatsapp-baileys 2>/dev/null" | grep -oE "[0-9a-f-]{36}" | head -1)
  echo ">> instância criada: $ID"
else
  echo ">> instância existente: $ID"
fi
[ -n "$ID" ] || { echo "falha ao obter o instance ID" >&2; exit 1; }

# 3. conecta e espera o estado 'qr' (a janela do pairing code exige a sessão conectada;
#    a 1ª conexão pode cair p/ 'disconnected' — reconecta no loop).
for try in 1 2; do
  om "omni instances connect $ID" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    st=$(om "omni instances status $ID 2>/dev/null" | awk '/^state/{print $2}')
    [ "$st" = "qr" ] && break 2
    [ "$st" = "connected" ] && { echo ">> instância JÁ conectada (pareada antes). Pule para: make sandbox-connect"; exit 0; }
    sleep 1
  done
done

# 4. gera o pairing code.
echo ">> gerando pairing code p/ $PHONE …"
om "omni instances pair $ID --phone $PHONE" 2>&1 | grep -iE "Pairing code|\"code\"|expires|Enter this" || \
  { echo "falha ao gerar o pairing code (reconecte: rode de novo)"; exit 1; }
cat <<EOF

>> Digite o código acima NO CELULAR DO BOT (expira em ~60s):
   WhatsApp → Aparelhos conectados → Conectar um aparelho → "Conectar com número".
   Se expirar, rode 'make sandbox-pair PHONE=$PHONE' de novo.
   Conectou? Próximo: make sandbox-connect
EOF
