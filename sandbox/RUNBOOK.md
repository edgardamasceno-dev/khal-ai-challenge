# Runbook — Sandbox Omni/Genie + agente CX (login + E2E)

Passo a passo reprodutível para colocar o agente CX `luz-do-vale` atendendo, do
zero. As etapas **interativas** (login, QR) são suas; as **determinísticas**
(subir stack, wiring, E2E interno) são automatizáveis.

Pré-requisitos: Docker; imagem `khal-sandbox:base` buildada
(`docker build -f sandbox/Dockerfile -t khal-sandbox:base .` a partir da raiz);
imagem do egress (`docker build -t khal-egress-proxy sandbox/egress`).

---

## 1. Subir o stack (determinístico)

A partir da raiz do repo (`implementation/`):

```bash
docker compose \
  -f docker-compose.yml \
  -f sandbox/compose.sandbox.yml \
  up -d --force-recreate mcp-server egress-proxy sandbox
```

Sobe: `database`, `backend`, `mcp-server` (em `mcpnet`), `egress-proxy`, `sandbox`.
O `sandbox` fica em `sleep infinity` (operador dirige os passos abaixo).

**Checagem de isolamento** (o sandbox só enxerga o MCP):

```bash
docker exec khal-sandbox sh -c '
  curl -s -o /dev/null -w "mcp-server -> %{http_code} (espera 406)\n"  http://mcp-server:8000/mcp
  curl -s -o /dev/null -w "backend    -> %{http_code} (espera 000)\n" --max-time 4 http://backend:8000/health
  curl -s -o /dev/null -w "database   -> %{http_code} (espera 000)\n" --max-time 4 http://database:5432'
```

---

## 2. `claude login` (INTERATIVO — você)

O agente usa o Claude Code reutilizando seu login (ADR-0007, sem API key). O
login persiste no volume `claude-home` (`~/.claude`, **não** versionado).

```bash
docker exec -it khal-sandbox claude login
```

Siga o fluxo OAuth (abra a URL, cole o código). Confirme:

```bash
docker exec khal-sandbox claude --version
docker exec khal-sandbox sh -c 'ls -la /home/node/.claude/'   # credenciais persistidas
```

> O login sobrevive a `up -d` futuros (volume). Só refaça se trocar de conta.

---

## 3. Wiring do agente CX + MCP (determinístico)

Monta `agents/luz-do-vale/AGENTS.md` (frontmatter de tool-scoping + persona da
entrega bind-mounted) e registra o MCP no Claude Code:

```bash
docker exec khal-sandbox bash /srv/genie-wire.sh
# espere: "luz-do-vale: http://mcp-server:8000/mcp (HTTP) - ✓ Connected"
docker exec khal-sandbox claude mcp get luz-do-vale
```

---

## 4. Subir os daemons + genie serve (determinístico)

```bash
docker exec -d khal-sandbox sh -c 'bash /srv/sandbox-up.sh > /tmp/up.log 2>&1'
# aguarde a convergência:
docker exec khal-sandbox sh -c '
  for i in $(seq 1 90); do grep -q "genie serve is running" /tmp/up.log && break; sleep 1; done
  grep -iE "Omni bridge|Agent sync|Listening on omni|serve is running" /tmp/up.log'
```

Espere: postgres-genie `:19642`, NATS `:4222`, Omni API `:8882`,
`Agent sync: ... registered` (inclui `luz-do-vale`), `Omni bridge started`,
`Listening on omni.message.>`, `genie serve is running`.

---

## 5. E2E interno — NATS → bridge → agente → MCP (determinístico, sem WhatsApp)

Publica uma mensagem como se viesse do WhatsApp e observa o agente processando.
O telefone do remetente (`sender`) é a identidade do cliente — use uma persona do
seed (ex. Ana Souza). Subject: `omni.message.<instância>.<chat>`. O payload é o
`OmniMessage` real do Genie: `{ content, sender, instanceId, chatId, agent }`.

> **Importante:** a *entrega* da resposta sai por `omni say` → Omni API → Baileys →
> WhatsApp. **Sem instância pareada (passo 6), o reply final não egressa.** O que
> se valida internamente é a malha **NATS → bridge → spawn do agente → tool-calls
> no MCP** + o texto da resposta no painel tmux. A entrega ponta-a-ponta é o passo 6.

> **Corrida no spawn a frio (importante):** a **1ª** `omni.message` de um chat
> *cria* a sessão tmux do agente, mas pode não entrar na TUI a tempo (a entrega
> corre com o bootstrap do Claude Code) — o painel fica no prompt vazio. A **2ª**
> mensagem (sessão já ativa) entra via `deliver()` e roda normal. **Mitigação:**
> reenvie a 1ª mensagem, ou mande um `oi` de aquecimento antes da mensagem real.

Resultado já observado (E2E interno, persona Ana Souza): o agente fez **11**
chamadas `mcp__luz-do-vale__*` (find_customer → outage → invoice) com dados reais
do seed e respondeu via `omni say`/`omni done` (`Bash(omni:*)` escopado) —
ex.: *"…interrupção ativa no seu bairro (Jardim das Flores), retorno hoje às 21h30…"*.

Publicar o evento (o client `nats` resolve em `/srv/genie`, API v2 com `StringCodec`):

```bash
docker exec khal-sandbox sh -c '
  cd /srv/genie && bun -e "
    import { connect, StringCodec } from \"nats\";
    const sc = StringCodec();
    const nc = await connect({ servers: \"localhost:4222\" });
    // acompanha o ciclo do turno (heartbeat/done) e descobre a instância/chat:
    const sub = nc.subscribe(\"omni.>\");
    (async () => { for await (const m of sub) console.log(\"NATS:\", m.subject, sc.decode(m.data).slice(0,120)); })();
    const chat = \"555199990001\";                       // telefone da Ana (ajuste ao .env)
    nc.publish(\`omni.message.demo.\${chat}\`, sc.encode(JSON.stringify({
      content: \"oi, minha luz caiu, e a minha fatura?\",
      sender: chat, chatId: chat, instanceId: \"demo\", agent: \"luz-do-vale\"
    })));
    await new Promise(r => setTimeout(r, 90000));        // aguarda o turno
    await nc.drain();
  "'
```

Em paralelo, observe a malha:

```bash
docker exec khal-sandbox sh -c 'tail -n 40 -f /tmp/up.log'      # omni-bridge: recebeu / spawnou
docker logs -f khal-mcp                                          # tool-calls chegando no MCP (prova a via)
docker exec khal-sandbox sh -c 'tmux -L genie ls; tmux -L genie capture-pane -p -t <janela>'  # raciocínio + reply
```

**Critério de sucesso (interno):** o bridge loga `NATS message received ... agent=luz-do-vale`,
spawna o agente, e o `khal-mcp` registra chamadas `find_customer_by_phone` →
`get_invoice_status`/`get_outage_by_region`; no painel tmux o agente compõe a
resposta com dados **reais** do seed e tenta `omni say` + `omni done`.
A entrega real ao WhatsApp é o passo 6.

---

## 6. E2E WhatsApp real (INTERATIVO — você) — fluxo validado

Dois números: **bot** (escaneia/parea, recebe e responde) e **cliente** (manda a
mensagem; precisa estar no seed). São WhatsApp distintos — não dá pra ser o mesmo.

### 6.0 Rede direta p/ o Baileys (WSS)

O WebSocket do Baileys (`wss://web.whatsapp.com/ws/chat`) **não honra `HTTP_PROXY`**
e o sandbox não tem internet direta (só `mcpnet`+`egressnet` internas). Conecte o
sandbox a uma rede **não-interna** (mantém backend/database inalcançáveis = só-MCP;
abre mão do allowlist de egress p/ o processo omni/Baileys):

```bash
docker network create khal-wanet 2>/dev/null || true
docker network connect khal-wanet khal-sandbox
# valida: WSS direto OK, negócio ainda bloqueado:
docker exec khal-sandbox sh -c 'curl -s -o /dev/null -w "wa %{http_code}\n" --noproxy "*" https://web.whatsapp.com; \
  curl -s -o /dev/null -w "backend %{http_code} (espera 000)\n" --noproxy "*" --max-time 4 http://backend:8000/health'
```

### 6.1 Autentica o CLI do omni

A API gera uma key a cada start (pgserve do omni é efêmero). Pegue do log e logue:

```bash
KEY=$(docker exec khal-sandbox sh -c 'grep -oE "omni_sk_[A-Za-z0-9]+" /tmp/omni-api.log | head -1')
docker exec khal-sandbox sh -c "cd /srv/omni && omni auth login --api-key $KEY"
```

### 6.2 Cria a instância e parea (pairing code — mais robusto que o QR rotativo)

```bash
ID=$(docker exec khal-sandbox sh -c 'cd /srv/omni && omni instances create \
  --name luzdovale-bot --channel whatsapp-baileys 2>/dev/null' | grep -oE "[0-9a-f-]{36}" | head -1)
docker exec khal-sandbox sh -c "cd /srv/omni && omni instances connect $ID"
sleep 4
# código de 8 chars p/ o número do BOT (com DDI):
docker exec khal-sandbox sh -c "cd /srv/omni && omni instances pair $ID --phone +1XXXXXXXXXX"
```

No celular do **bot**: WhatsApp → Aparelhos conectados → Conectar um aparelho →
**"Conectar com número de telefone"** → digite o código. (Alternativa: QR ASCII com
`omni instances qr $ID`, mas roda a cada ~20s — o código é mais confiável.)

```bash
docker exec khal-sandbox sh -c "cd /srv/omni && omni instances status $ID"   # -> connected
```

### 6.3 Liga a instância ao agente (com env force-TCP do genie)

O `omni connect` descobre o agente no diretório do genie via pgserve — passe as
envs force-TCP (nosso genie roda assim):

```bash
docker exec khal-sandbox sh -c "cd /srv/omni && \
  GENIE_PG_FORCE_TCP=1 GENIE_PG_PORT=19642 GENIE_DB_NAME=genie PGPASSWORD=postgres \
  omni connect $ID luz-do-vale"
```

### 6.4 LID: chaveie o cliente pelo identificador que o WhatsApp envia

O WhatsApp manda um **LID** (`<digitos>@lid`), **não** o telefone E.164. Descubra o
LID do cliente (mande uma msg dele e veja o `from`/`chatId` em `/tmp/omni-api.log`)
e re-seede a persona chaveada por esse LID (perfil rico por ser persona única):

```bash
# ex.: LID 87866608713902
docker compose -f docker-compose.yml run --rm \
  -e 'SEED_PERSONAS=Edgar Damasceno:87866608713902' seed
```

> Adaptação de demo. O ideal — resolver **LID→telefone** no omni (`chat_id_mappings`)
> — fica como follow-up para usar o número E.164 real.

### 6.5 Teste e observe

Mande um WhatsApp do **cliente** para o **bot**. Observe:

```bash
docker exec khal-sandbox sh -c 'grep -iE "Received|Published to NATS" /tmp/omni-api.log | tail'
docker exec khal-sandbox sh -c 'tmux -L genie capture-pane -p -t luz-do-vale:1'   # turno do agente
docker logs khal-mcp | grep -c CallToolRequest                                     # tool-calls
docker exec khal-sandbox sh -c 'grep "POST /api/v2/messages/send" /tmp/omni-api.log | tail'  # 201 = enviado
```

**Sucesso:** o agente chama `find_customer_by_phone` (casa o LID) →
`get_invoice_status`/`get_outage_by_region` → `omni say` (`POST .../messages/send → 201`)
→ `omni done`. A resposta chega no WhatsApp do cliente com os dados reais do seed.

### Notas operacionais
- **Auth do agente:** se o container foi **recriado** depois do `claude login`, refaça
  `docker exec -it khal-sandbox claude login` (a sessão TUI do Claude Code atrela ao
  container; o `claude -p` segue funcionando, mas o spawn TUI cai no OAuth).
- **Corrida do 1º spawn:** a 1ª mensagem de um chat cria a sessão e pode não entrar na
  TUI — reenvie. Se você matou janelas tmux no diagnóstico, limpe os resíduos de sessão:
  `delete from genie_bridge_sessions where chat_id ilike '%<lid>%'` (DB genie, `:19642`).

---

## Guardrails ativos nesta topologia

- **Rede só-MCP:** o sandbox alcança o **negócio apenas via `mcp-server`**; sem rota
  a `backend`/`database` (validado: → 000). Vale mesmo com a rede direta do passo 6.
- **Egress:** o agente (Claude Code) sai pelo `egress-proxy` allowlistado
  (Anthropic + WhatsApp). Com a `khal-wanet` (passo 6) o processo omni/Baileys ganha
  internet direta (WSS) — relaxa o allowlist p/ a infra, mas o **agente** segue contido
  pelo tool-scoping (sem WebFetch/WebSearch/Bash livre).
- **Tool-scoping:** o Claude Code spawna com allow = `mcp__luz-do-vale__*` +
  `Bash(omni:*)`; `--disallowedTools` em WebFetch/WebSearch/escrita/Task.
- **Acesso só ao titular:** resolvido pelo telefone do remetente (no MCP/persona),
  não contornável por injection.
- **Confirmação antes de escrever** (`create_ticket`) + idempotência — no MCP.
