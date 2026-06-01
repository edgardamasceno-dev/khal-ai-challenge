# Runbook — Sandbox Omni/Genie + agente CX (login + E2E)

Passo a passo reprodutível para colocar o agente CX `luz-do-vale` atendendo, do
zero. As etapas **determinísticas** são `make` targets; as **interativas** (login OAuth,
pareamento do WhatsApp) são suas e estão marcadas como tal.

**Fluxo rápido (do zero ao E2E interno provado):**

```bash
make sandbox-up       # 1. determinístico  — vendor + build + overlay + backend/worker wired ao Omni
make sandbox-login    # 2. INTERATIVO (você) — claude login (device-flow, persiste no volume)
make sandbox-serve    # 3+4. determinístico — wiring do agente + daemons (NATS/Omni/genie serve)
make sandbox-smoke    # 5. determinístico  — self-test: prova NATS→bridge→agente→MCP (exit≠0 se falhar)
# 6. WhatsApp real (precisa de 2 celulares: bot + cliente):
make sandbox-pair PHONE=+<DDI><bot>         # 6.1+6.2 → você digita o código no celular do BOT
make sandbox-connect                        # 6.3 liga a instância ao agente
#   -> mande a msg do CLIENTE -> o LID resolve sozinho (SPEC-015/030) -> resposta no WhatsApp (6.5)
make sandbox-media-on                       # 6.6 (opt-in) PDF da 2ª via como ANEXO (default = só link)
#   Derrubar tudo: make sandbox-down
```

> **SPEC-030**: o `make sandbox-up` já cria a `khal-wanet` e conecta `sandbox`+`backend`+`worker`
> (a Omni API roda no sandbox, aliased `omni`). Então **não há passo de rede manual** (`sandbox-wanet`
> virou diagnóstico opcional — §6.0) **nem de re-seed**: o LID resolve sozinho e o instance-id é
> descoberto pelo nome (`luzdovale-bot`). `OMNI_API_KEY` fixo no `.env`; `OMNI_INSTANCE_ID` fica vazio.

> `make sandbox-up` recria o container, mas o login (volume `claude-home`) e o pgdata do Genie
> (R-05) **sobrevivem**; o `sandbox-serve` re-marca o onboarding do Claude automaticamente — então
> repetir o ciclo **não** exige refazer o `claude login` (só se trocar de conta / volume novo).

Pré-requisitos: Docker. A parte **determinística** (vendorizar os clones pinados de Omni/Genie
em `sandbox/libs/`, buildar as imagens `khal-sandbox:base` e `khal-egress-proxy` + subir o
overlay isolado) é encapsulada em **`make sandbox-up`** (Etapa 1) — inclusive o vendoring
(`sandbox-libs`: clona se faltar e fixa em `genie@a407a2e2` / `omni@fe155b81`, doc 07).
Equivalente manual: clones em `sandbox/libs/` (ver `sandbox/README.md`) +
`docker build -f sandbox/Dockerfile -t khal-sandbox:base .` (a partir da raiz) +
`docker build -t khal-egress-proxy sandbox/egress`.

---

## 1. Subir o stack (determinístico)

A partir da raiz do repo (`implementation/`), um comando builda as imagens do sandbox
e sobe o overlay isolado:

```bash
make sandbox-up
```

Equivale a vendorizar `sandbox/libs/` (`make sandbox-libs`) + `docker build` das 2 imagens +
`docker compose -f docker-compose.yml -f sandbox/compose.sandbox.yml up -d --build --force-recreate
mcp-server egress-proxy sandbox backend notifications-worker`.
Sobe: `database`, `backend`, `mcp-server` (em `mcpnet`), `egress-proxy`, `sandbox` e
`notifications-worker` (SPEC-030: `sandbox`+`backend`+`worker` também na `khal-wanet`).
O `sandbox` fica em `sleep infinity` (operador dirige os passos abaixo). Derrubar: `make sandbox-down`.

**Checagem de rede** (o `mcp-server` é a via de tools do agente; pós-SPEC-030 o `backend` é
alcançável em L3 pela `khal-wanet` — o isolamento forte é o do **agente** por tool-scoping):

```bash
docker exec khal-sandbox sh -c '
  curl -s -o /dev/null -w "mcp-server -> %{http_code} (espera 406)\n"  http://mcp-server:8000/mcp
  curl -s -o /dev/null -w "backend    -> %{http_code} (SPEC-030: alcançável em L3; o AGENTE não o acessa fora do MCP — tool-scoping)\n" --max-time 4 http://backend:8000/health'
```

---

## 2. `claude login` (INTERATIVO — você)

O agente usa o Claude Code reutilizando seu login (ADR-0007, sem API key). O
login persiste no volume `claude-home` (`~/.claude`, **não** versionado).

```bash
make sandbox-login        # = docker exec -it khal-sandbox claude login
```

Siga o fluxo OAuth (abra a URL, cole o código). Confirme:

```bash
docker exec khal-sandbox claude --version
docker exec khal-sandbox sh -c 'ls -la /home/node/.claude/'   # credenciais persistidas
```

> O login sobrevive a `up -d` futuros (volume). Só refaça se trocar de conta.

---

## 3. Wiring do agente CX + MCP (determinístico — embutido no `make sandbox-serve`)

Monta `agents/luz-do-vale/AGENTS.md` (frontmatter de tool-scoping + persona da
entrega bind-mounted + bloco KB/CAG) e registra o MCP no Claude Code. **O `sandbox-up.sh`
(Etapa 4) já roda o `genie-wire.sh`**, então normalmente você não precisa rodá-lo à mão —
está aqui para inspeção/debug isolado:

```bash
docker exec khal-sandbox bash /srv/genie-wire.sh
# espere: "luz-do-vale: http://mcp-server:8000/mcp (HTTP) - ✓ Connected"
docker exec khal-sandbox claude mcp get luz-do-vale
```

---

## 4. Subir os daemons + genie serve (determinístico)

```bash
make sandbox-serve
```

Encadeia (via `/srv/sandbox-up.sh`, detached em `/tmp/up.log`): postgres-genie `:19642`,
NATS/JetStream `:4222`, Omni API `:8882`, **wiring do agente** (Etapa 3), **re-mark de
onboarding do Claude** (passo 5b, sobrevive a recreate) e `genie serve`. Espera o
`genie serve is running` e **falha (exit 1)** se não convergir em 120s. Espere ainda:
`Agent sync: … registered` (inclui `luz-do-vale`), `Listening on omni.message.>`.

> Roda **uma vez** sobre um sandbox recém-subido (`make sandbox-up`). Os daemons abrem portas
> fixas; não re-execute no mesmo container sem antes recriá-lo (`make sandbox-up`).

Equivalente manual:

```bash
docker exec -d khal-sandbox sh -c 'bash /srv/sandbox-up.sh > /tmp/up.log 2>&1'
docker exec khal-sandbox sh -c 'for i in $(seq 1 120); do grep -q "genie serve is running" /tmp/up.log && break; sleep 1; done; tail -5 /tmp/up.log'
```

---

## 5. E2E interno — NATS → bridge → agente → MCP (determinístico, sem WhatsApp)

```bash
make sandbox-smoke
```

Self-test reproduzível: resolve uma persona do **seed** (telefone E.164 do titular),
publica uma `omni.message` sintética de aquecimento + a real, e **afirma** a malha
`NATS → bridge → spawn → tool-calls no MCP` — `SMOKE OK` com exit 0, ou `SMOKE FAIL`
com exit ≠ 0 (não passa por engano). Tunável: `SMOKE_WARMUP`/`SMOKE_WAIT` (segundos).
A *entrega* real (`omni say` → WhatsApp) **não** é exigida aqui — é a Etapa 6.

Para inspecionar/customizar à mão (o `make sandbox-smoke` faz isto por você): publica uma
mensagem como se viesse do WhatsApp. O telefone do remetente (`sender`) é a identidade do
cliente — use uma persona do seed. Subject: `omni.message.<instância>.<chat>`. Payload = o
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

### 6.0 Rede do Baileys (WSS) — já feita pelo `sandbox-up` (SPEC-030)

O WebSocket do Baileys (`wss://web.whatsapp.com/ws/chat`) **não honra `HTTP_PROXY`**, então o
sandbox precisa de uma rede **não-interna**. **Desde a SPEC-030 isso é automático**: o
`make sandbox-up` cria a `khal-wanet` e põe `sandbox`+`backend`+`worker` nela — a MESMA rede que
o backend usa p/ alcançar a Omni API (resolução do LID + envio). Então **não rode nada aqui**.

`make sandbox-wanet` continua como **diagnóstico opcional** (idempotente): confirma que o sandbox
alcança `web.whatsapp.com`. **Atenção ao isolamento (SPEC-030):** o `backend` agora **é**
alcançável em L3 pelo sandbox (compartilham a `khal-wanet`, pois a Omni roda dentro do sandbox) —
o check antigo "backend→000" deixou de valer. O isolamento forte é o do **agente** (tool-scoping:
só `mcp__luz-do-vale__*` + `Bash(omni:*)`; sem `curl`/`WebFetch`), não o de rede do container.

### 6.1 + 6.2 — Autentica + cria a instância + gera o pairing code

```bash
make sandbox-pair PHONE=+<DDI><numero-do-bot>      # ex.: PHONE=+16472015092
```

Faz toda a cola CLI: omni auth (key efêmera do log) + cria/reusa a instância `luzdovale-bot`
+ conecta o Baileys + imprime o **pairing code** de 8 chars (mais robusto que o QR rotativo).
**Sua única ação física:** digite o código no celular do **bot** — WhatsApp → Aparelhos
conectados → Conectar um aparelho → **"Conectar com número de telefone"**. Expira em ~60s;
se expirar, rode `make sandbox-pair PHONE=…` de novo (idempotente, reusa a instância).

Equivalente manual: `omni auth login --api-key <key do /tmp/omni-api.log>` + `omni instances
create --name luzdovale-bot --channel whatsapp-baileys` + `omni instances connect <id>` +
`omni instances pair <id> --phone +<DDI><numero>`.

### 6.3 — Liga a instância ao agente

```bash
make sandbox-connect
```

Resolve o instance-ID pelo nome e roda `omni connect <id> luz-do-vale` (com as envs
force-TCP do postgres do genie). Pré-req: você já pareou o código (status `connected`).

### 6.4 — LID: resolução automática (SPEC-015 + SPEC-030, sem reseed)

O WhatsApp manda um **LID** (`<dígitos>@lid`), **não** o telefone E.164. Isso é resolvido
**automaticamente**: o backend chama `resolve_canonical` no Omni (`GET /api/v2/chats`:
`externalId <lid>@lid` ↔ `canonicalId <msisdn>@s.whatsapp.net`) e acha o titular pelas
variantes de nono dígito (**SPEC-015**). Para isso disparar, o **wiring backend↔Omni**
(SPEC-030) precisa estar de pé — e já está, pelo `make sandbox-up`:

- `OMNI_API_KEY` **fixo** (`.env`) compartilhado entre backend e a Omni API do sandbox
  (sem ele, a key efêmera do Omni dá 401 e a resolução cai);
- o `sandbox` aliased como **`omni`** na `khal-wanet`, e `backend`/`worker` na mesma rede.

Então **não há passo de re-seed**: mande a mensagem do cliente e o agente já reconhece o
titular. (Se o backend não estiver wired, a resolução cai e o cliente vira "não identificado"
— cheque `OMNI_API_KEY` no `.env` e se backend/worker estão na `khal-wanet`.)

> Trade-off de isolamento (SPEC-030/ADR-0006): `backend`/`worker` compartilham a `khal-wanet`
> com o `sandbox` (a Omni API roda **dentro** do container do sandbox), então a rota L3
> backend↔sandbox existe — **a mesma** que o proativo (SPEC-009) já exige. O **agente** segue
> isolado por **tool-scoping** (só `mcp__luz-do-vale__*` + `Bash(omni:*)`; sem `curl`/`WebFetch`):
> ele **não** alcança o negócio fora do MCP. O isolamento forte é o do agente, não o de rede do container.

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

### 6.6 Anexo da 2ª via (PDF) — opt-in de mídia (SPEC-019 / ADR-0010)

No demo, o **link presigned é `localhost`** — alcançável só na máquina local / WhatsApp Web (não
de um celular físico), e o agente o suprime por padrão. Então o **PDF anexo** é o caminho de
entrega: o upload do Baileys precisa subir aos CDNs (`mmg`/`*.cdn.whatsapp.net`) sem o proxy (o
`fetch` do Bun não tuneliza upload com streaming via `CONNECT`). O `NO_PROXY` do sandbox já lista
os CDNs (`compose.sandbox.yml`); falta só a rota direta. Opt-in (default da entrega = isolado):

```bash
make sandbox-media-on      # = bash sandbox/enable-media.sh (conecta a `bridge`)
#   -> re-peça a 2ª via no WhatsApp; o PDF chega como ANEXO.
make sandbox-media-off     # = bash sandbox/disable-media.sh (restaura o isolamento)
```

Teste E2E direto pelo backend (titular real, sem depender do turno do agente):

```bash
bash sandbox/enable-media.sh      # (idem make sandbox-media-on)
# teste E2E (titular real):
FID=$(docker exec khal-database psql -U khal -d khal -tAc \
  "select f.id from faturas f join unidades_consumidoras u on u.id=f.uc_id \
   join titulares t on t.id=u.titular_id where t.telefone_principal='<seu_numero>' \
   order by f.vencimento desc limit 1" | tr -d ' ')
docker exec khal-backend python -c "import urllib.request; \
  print(urllib.request.urlopen(urllib.request.Request('http://localhost:8000/invoices/$FID/send', \
  data=b'{}', headers={'Content-Type':'application/json'}, method='POST')).read().decode())"
# espera: "enviado_anexo": true   (send/media -> 201 em ~2-3s)

bash sandbox/disable-media.sh     # restaura o isolamento (volta a só o link)
```

Sem `enable-media.sh`: `enviado_anexo: false` e a 2ª via sai só pelo **link** (fallback
best-effort da SPEC-017) — o isolamento de rede do default (ADR-0006) fica intacto. Usa a
`bridge` (não a `khal-wanet` do 6.0): o WSS conecta por ambas, mas o upload via Bun `fetch` só
completa pela `bridge` (ver ADR-0010).

### Notas operacionais
- **Auth do agente (recriação):** o token do `claude login` persiste no volume `claude-home`
  (`~/.claude/.credentials.json`) e o `sandbox-up.sh` **re-marca o onboarding automaticamente**
  no startup (passo 5b) — então após um `--force-recreate` o spawn TUI do agente volta a
  funcionar **sem refazer login**. Só refaça `docker exec -it khal-sandbox claude login` se a
  credencial em si expirou/sumiu (volume novo). Causa: a credencial fica no volume, mas o estado
  de onboarding vive em `~/.claude.json` (arquivo irmão, **fora** do volume, resetado no recreate)
  — daí o re-mark em runtime. Se mesmo assim o pane cair em "Select login method", limpe a sessão
  obsoleta do chat (`delete from genie_bridge_sessions where chat_id=...` no PG do genie :19642) e
  reinicie o `genie serve` — o spawn seguinte nasce limpo.
- **Corrida do 1º spawn:** a 1ª mensagem de um chat cria a sessão e pode não entrar na
  TUI — reenvie. Se você matou janelas tmux no diagnóstico, limpe os resíduos de sessão:
  `delete from genie_bridge_sessions where chat_id ilike '%<lid>%'` (DB genie, `:19642`).

---

## 7. Cold-start estrutural (R-05) e hooks de guardrail (R-20)

Duas evoluções da sandbox, ambas **mínimas e reversíveis** — não alteram o fluxo
dos passos 1–6 quando desabilitadas.

### 7.1 R-05 — pgdata do Genie em volume nomeado (persistência do cold-start)

O `compose.sandbox.yml` agora monta `GENIE_PGDATA=/home/node/.genie-pgdata` no
**volume nomeado `genie-pgdata`**. O estado do postgres dedicado do Genie
(sessões/bridge) sobrevive a `--force-recreate` — casado com o `--resume` do Genie,
o **cold-start vira custo pago uma vez por chat na vida** (não a cada recriação).

> **Ownership do volume (validação ao vivo):** um volume nomeado montado num path
> que **não existia** na imagem nasce `root`-owned, e o `initdb` (non-root) falharia.
> O `sandbox-up.sh` (bloco 0) **detecta isso e cai em FALLBACK** para o FS efêmero
> com aviso — o sandbox **nunca quebra**, só não persiste. Para ativar a
> persistência de fato, o mountpoint precisa ser `node`-gravável. Verifique:
> ```bash
> docker exec khal-sandbox sh -c 'ls -ld /home/node/.genie-pgdata && touch /home/node/.genie-pgdata/.w && echo gravável && rm /home/node/.genie-pgdata/.w'
> ```
> Se aparecer "gravável", o `initdb` persiste no volume. Se vier `Permission denied`,
> o follow-up é pré-criar o dir `node`-owned no `Dockerfile` (como já se faz com
> `~/.claude`), e então recriar a sandbox. **Reverter:** remova a env `GENIE_PGDATA`
> e o volume `genie-pgdata` do `compose.sandbox.yml` (volta ao FS efêmero de antes).

**Validar a persistência (ao vivo):** suba a stack, conecte um chat (passo 5/6),
depois `up -d --force-recreate sandbox` e confirme que a sessão re-anexa via
`--resume` (não refaz cold-start). A linha de sessão deve persistir:
```bash
docker exec khal-sandbox sh -c 'PGPASSWORD=postgres psql -h 127.0.0.1 -p 19642 -U postgres -d genie -tAc "select chat_id from genie_bridge_sessions limit 5"'
```

### 7.2 R-05 — warm-pool determinístico (opt-in) + heartbeat

O `sandbox-up.sh` publica, **se** `WARM_POOL_PHONES` estiver setado, 1 `omni.message`
sintética de aquecimento por telefone-âncora **após** o serve subir — o 1º turno
real do cliente cai numa sessão já quente (mata a corrida do 1º spawn). **Default
vazio = desligado** (comportamento idêntico ao de antes).

Habilitar (telefones das personas-âncora do seu `.env`, espaço ou vírgula):
```bash
docker exec -d khal-sandbox sh -c 'WARM_POOL_PHONES="555199990001 555199990002 555199990003" bash /srv/sandbox-up.sh > /tmp/up.log 2>&1'
docker exec khal-sandbox sh -c 'grep -i "warm-pool" /tmp/up.log'   # "aquecido <phone>"
```

**Heartbeat anti-nudge (validação ao vivo):** turnos longos (PDF/multi-tool) não
podem morrer no nudge de 120s. Confirme o `agent-heartbeat` (~30s) nos logs do serve:
```bash
docker exec khal-sandbox sh -c 'grep -i "heartbeat" /tmp/up.log | tail'
```

**Invalidação de sessão por hash (R-05):** o `--resume` reanexa o pane; se a
persona/tool-set mudou, a sessão antiga teria prompt obsoleto. O fingerprint
determinístico `src/agent/session_hash.py::session_fingerprint` (persona +
frontmatter + catálogo de tools na ordem canônica) é a base para invalidar
(`clear-session`/`delete from genie_bridge_sessions`) quando o hash diverge.
A função é **pura e testada offline** (`tests/unit/test_guardrail_hook.py`); o
disparo no sandbox é validação ao vivo (o sandbox não monta `src/` Python).

### 7.3 R-20 — hooks de guardrail determinístico do Claude Code

4ª camada de guardrail, **no runtime do agente**, complementando tool-scoping +
rede só-MCP + validação no MCP. O `genie-wire.sh` (passo 3) copia
`sandbox/agent/settings.json` para `~/.claude/settings.json` (escopo user,
volume `claude-home`), registrando dois hooks que chamam
`/srv/agent/hooks/guardrail.py` (bind-mount read-only):

- **PreToolUse** — bloqueia tool MCP fora da allowlist, `create_ticket` sem
  `confirmar=true`, e telefone diferente do remetente do turno.
- **UserPromptSubmit** — bloqueia prompt-injection óbvio no texto do cliente.

A lógica é pura (`decidir(evento) -> (permitido, motivo)`), unit-testada em
`tests/unit/test_guardrail_hook.py` (inclui smoke do script via stdin → exit
0/2 e paridade da allowlist do hook com `src/interfaces/mcp/allowlist.py`).

Verificar o registro (após o wiring):
```bash
docker exec khal-sandbox sh -c 'cat ~/.claude/settings.json | python3 -m json.tool | head'
docker exec khal-sandbox sh -c 'echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"mcp__luz-do-vale__create_ticket\",\"tool_input\":{\"confirmar\":false}}" | python3 /srv/agent/hooks/guardrail.py; echo "exit=$?"'   # espera exit=2 + motivo no stderr
```

> **Validação ao vivo:** o *disparo* dos hooks pelo Claude Code depende de o spawn
> do Genie repassar o settings de escopo user — confirme no E2E (passo 5/6) que um
> `create_ticket` sem confirmação é barrado. **Reverter:** remova
> `~/.claude/settings.json` (ou não copie no wiring) — desliga os hooks sem afetar
> as demais camadas.

---

## Guardrails ativos nesta topologia

- **Tool-scoping (não rede):** o **agente** (Claude Code) alcança o **negócio apenas via
  `mcp-server`** (+ `Bash(omni:*)`). Pós-SPEC-030 o `backend` **é** alcançável em L3 pela
  `khal-wanet` (mesma rede do Omni, que roda dentro do sandbox), mas o agente **não** o acessa
  fora do MCP (sem `WebFetch`/`WebSearch`/`Bash` livre). O isolamento forte é o do **agente**
  por tool-scoping, **não** o de rede do container (ADR-0006). O `database` segue sem rota.
- **Egress:** o agente (Claude Code) sai pelo `egress-proxy` allowlistado
  (Anthropic + WhatsApp). Com a `khal-wanet` (passo 6) o processo omni/Baileys ganha
  internet direta (WSS) — relaxa o allowlist p/ a infra, mas o **agente** segue contido
  pelo tool-scoping (sem WebFetch/WebSearch/Bash livre).
- **Tool-scoping:** o Claude Code spawna com allow = `mcp__luz-do-vale__*` +
  `Bash(omni:*)`; `--disallowedTools` em WebFetch/WebSearch/escrita/Task.
- **Acesso só ao titular:** resolvido pelo telefone do remetente (no MCP/persona),
  não contornável por injection.
- **Confirmação antes de escrever** (`create_ticket`) + idempotência — no MCP.
- **Hooks de guardrail (R-20):** 4ª camada no runtime do agente (PreToolUse +
  UserPromptSubmit) — barra tool fora da allowlist, escrita sem confirmação,
  telefone ≠ remetente e prompt-injection óbvio. Determinístico, no código
  (`sandbox/agent/hooks/guardrail.py`), testado offline; ver §7.3.
