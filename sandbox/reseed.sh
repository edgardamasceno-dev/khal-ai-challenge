#!/usr/bin/env bash
# make sandbox-reseed [LID=...] — Etapa 6.4 do RUNBOOK (ADAPTAÇÃO DE DEMO).
#
# Porquê: o seed chaveia o cliente pelo telefone E.164, mas o WhatsApp/Baileys manda o
# `sender` como um LID (`<dígitos>@lid`, identificador de privacidade), não o telefone.
# Então `find_customer_by_phone` (casa por dígitos) não acha o cliente. Aqui re-chaveamos
# a persona do `.env` pelo LID que o SEU WhatsApp manda — assim o agente te reconhece.
# (O ideal — resolver LID→telefone no Omni — é follow-up; ver RUNBOOK §6.4.)
#
# Auto-detecta o LID da última mensagem inbound no log do Omni. Override: make sandbox-reseed LID=...
# Pré-req: você já mandou ao menos UMA mensagem do celular cliente para o bot (após sandbox-connect).
set -euo pipefail

SB=khal-sandbox
LID="${1:-${LID:-}}"

# auto-detecta o LID (padrão <digitos>@lid; fallback jid <digitos>@s.whatsapp.net).
if [ -z "$LID" ]; then
  LID=$(docker exec "$SB" sh -lc 'grep -oE "[0-9]{6,}@lid" /tmp/omni-api.log 2>/dev/null | tail -1' | sed 's/@lid//')
  [ -n "$LID" ] || LID=$(docker exec "$SB" sh -lc 'grep -oE "[0-9]{6,}@s\.whatsapp\.net" /tmp/omni-api.log 2>/dev/null | tail -1' | sed 's/@s\.whatsapp\.net//')
fi
[ -n "$LID" ] || {
  echo "não achei um LID no log do Omni." >&2
  echo "Mande UMA mensagem do celular cliente para o bot (após make sandbox-connect) e rode de novo," >&2
  echo "ou passe explicitamente: make sandbox-reseed LID=<digitos>" >&2
  exit 1
}
echo ">> LID do cliente: …${LID: -6}"

# nome da persona do .env (1ª de SEED_PERSONAS="Nome:telefone;Nome2:...").
NAME=$(grep -E '^SEED_PERSONAS=' .env 2>/dev/null | sed -E 's/^SEED_PERSONAS=//; s/^["'\'']//; s/["'\'']$//' | cut -d';' -f1 | cut -d: -f1)
[ -n "$NAME" ] || NAME="Edgar Damasceno"
echo ">> re-seed: persona '$NAME' re-chaveada pelo LID (perfil derivado deterministicamente do LID)"

docker compose -f docker-compose.yml run --rm -e "SEED_PERSONAS=$NAME:$LID" seed 2>&1 | tail -6

cat <<EOF
>> pronto. Agora mande a mensagem REAL do cliente (ex.: "minha luz caiu, e a minha fatura?").
   O agente deve chamar find_customer_by_phone (casa o LID) → get_invoice_status/get_outage_by_region
   → omni say, e a resposta com dados reais chega no WhatsApp do cliente.
   Observe:  docker exec khal-sandbox sh -c 'tmux -L genie capture-pane -p -t luz-do-vale:1'
             docker logs khal-mcp | grep -c CallToolRequest
EOF
