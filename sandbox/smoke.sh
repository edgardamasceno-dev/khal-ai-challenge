#!/usr/bin/env bash
# Smoke test do E2E INTERNO do agente CX (RUNBOOK Etapa 5) — SEM WhatsApp.
#
# Publica uma `omni.message` SINTETICA de uma persona do seed e PROVA a malha
# determinística:  NATS -> omni-bridge -> spawn do agente (Claude/Genie) ->
# tool-calls no MCP `luz-do-vale`. A *entrega* real (omni say -> WhatsApp) é a
# Etapa 6 (interativa) e NÃO é exigida aqui — o critério é a malha + tool-calls.
#
# Robusto à CORRIDA DE COLD-START (a 1ª msg cria a sessão tmux + bootstrap do Claude,
# que pode passar da janela): REENVIA a mensagem (sessão já quente) e faz polling dos
# tool-calls até a malha fechar — a mitigação "reenvie" do RUNBOOK, automatizada.
#
# Pré-req:  make sandbox-up  ->  make sandbox-login  ->  make sandbox-serve.
# Uso:      make sandbox-smoke   (ou: bash sandbox/smoke.sh)
# Tunáveis: SMOKE_BOOT_WAIT (s, 1º envio/bootstrap, default 100),
#           SMOKE_RESEND_WAIT (s, por reenvio, default 45),
#           SMOKE_RETRIES (reenvios extra, default 3).
set -euo pipefail

SB=khal-sandbox          # container do sandbox (agente)
DB=khal-database         # Postgres do NEGÓCIO (host alcança; o sandbox NÃO)
MCP=khal-mcp             # MCP server (prova a via de tool-calls)
BOOT_WAIT="${SMOKE_BOOT_WAIT:-100}"
RESEND_WAIT="${SMOKE_RESEND_WAIT:-45}"
RETRIES="${SMOKE_RETRIES:-3}"
MSG="oi, minha luz caiu, e a minha fatura?"

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
mcp_calls() { docker logs "$MCP" 2>&1 | grep -c "CallToolRequest" || true; }
publish() {
  docker exec -e PHONE="$PHONE" -e MSG="$1" "$SB" sh -c 'cd /srv/genie && bun -e "
    import { connect, StringCodec } from \"nats\";
    const sc=StringCodec(); const nc=await connect({servers:\"localhost:4222\"});
    const chat=process.env.PHONE;
    nc.publish(\`omni.message.smoke.\${chat}\`, sc.encode(JSON.stringify({
      content:process.env.MSG, sender:chat, chatId:chat, instanceId:\"smoke\", agent:\"luz-do-vale\" })));
    await nc.drain();
  "' >/dev/null 2>&1
}

# 0. genie serve no ar?
docker exec "$SB" sh -lc 'grep -q "genie serve is running" /tmp/up.log' 2>/dev/null \
  || fail "genie serve não está no ar — rode: make sandbox-serve"

# 1. resolve a persona-cliente do seed (chave natural = telefone E.164 do titular).
PHONE=$(docker exec "$DB" psql -U khal -d khal -tAc \
  "select telefone_principal from titulares order by telefone_principal limit 1" 2>/dev/null | tr -d '[:space:]')
[ -n "$PHONE" ] || fail "nenhuma persona no seed (rode o seed: docker compose run --rm seed)"
echo ">> persona-cliente do seed: …${PHONE: -4}  (instanceId=smoke)"

# 2. baseline de tool-calls (delta isola ESTE smoke).
before=$(mcp_calls)

# 3. envia + reenvia até a malha fechar (cold-start self-healing).
found=0
for attempt in $(seq 0 "$RETRIES"); do
  if [ "$attempt" -eq 0 ]; then echo ">> envio 1 (cria a sessão + bootstrap; espera até ${BOOT_WAIT}s)"; w="$BOOT_WAIT";
  else echo ">> reenvio $((attempt+1)) (sessão quente; espera até ${RESEND_WAIT}s)"; w="$RESEND_WAIT"; fi
  publish "$MSG"
  for _ in $(seq 1 "$w"); do
    if [ "$(( $(mcp_calls) - before ))" -ge 1 ]; then found=1; break; fi
    sleep 1
  done
  [ "$found" -eq 1 ] && break
done

# 4. asserções da malha.
spawned=$(docker exec "$SB" sh -lc 'cat /tmp/up.log /tmp/serve*.log 2>/dev/null | grep -c "Spawning session for luz-do-vale" || true')
delta=$(( $(mcp_calls) - before ))
echo ">> bridge spawn(s)=$spawned | CallToolRequest deste smoke=+$delta"

echo "--- painel do agente (trecho) ---"
docker exec "$SB" sh -lc 'tmux -L genie capture-pane -p -t luz-do-vale:1 2>/dev/null | sed "/^[[:space:]]*$/d" | tail -8' || true
echo "----------------------------------"

[ "${spawned:-0}" -ge 1 ] || fail "o bridge não spawnou o agente (veja /tmp/up.log)"
[ "$delta" -ge 1 ]        || fail "o agente não chamou nenhuma tool no MCP após $((RETRIES+1)) envios (malha não fechou)"
echo "SMOKE OK ✅  malha NATS → bridge → agente → MCP provada (+$delta tool-calls). Entrega real = Etapa 6."
