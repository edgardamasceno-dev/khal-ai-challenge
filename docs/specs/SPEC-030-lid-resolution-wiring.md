# SPEC-030 - Resolução LID→telefone de verdade: wiring backend↔Omni (elimina o `sandbox-reseed`)

- Status: Approved (2026-06-01)
- Versao alvo: 1.x (o agente reconhece o cliente que liga por LID **sem** re-seed manual)
- ADRs: **ADR-0017** (ACL via MCP-over-REST — a resolução vive no backend, contrato MCP intacto),
  **ADR-0006** (isolamento do sandbox — preservado: o sandbox só alcança o MCP; o backend→Omni é a
  ponte de saída **já prevista** para o proativo). Relaciona-se com **SPEC-015** (resolução de LID,
  já Approved — esta SPEC **não** muda o algoritmo, só faz ele **disparar**) e **SPEC-009**
  (proativo, que já usa backend↔Omni).
- Substitui: `make sandbox-reseed` + `sandbox/reseed.sh` (adaptação de demo, RUNBOOK §6.4) — removidos.

## 1. Problema

`make sandbox-reseed` re-chaveia a persona pelo LID — um remendo de demo. Mas a **SPEC-015
(Approved) já resolve LID→telefone**: o agente passa o LID, o backend chama `resolve_canonical`
no Omni (`GET /api/v2/chats`: `externalId <lid>@lid` ↔ `canonicalId <msisdn>@s.whatsapp.net`) e
acha o titular pelas variantes de nono dígito.

**Provado ao vivo (2026-06-01):**
- O Omni **tem o mapeamento**: `externalId "87866608713902@lid"` → `canonicalId "558193112159@s.whatsapp.net"`.
- A lógica da SPEC-015 funciona: `normalizar_msisdn` → `558193112159`; `variantes_nono_digito` →
  `["558193112159","5581993112159"]`; o titular real `5581993112159` está nas variantes → casaria.

**Por que não dispara (e o reseed virou muleta):** o backend não autentica/alcança o Omni:
1. **`omni` não resolve.** `OMNI_URL=http://omni:8882` (compose + `.env`), mas nenhum container
   provê o alias `omni` na rede. O backend alcança `khal-sandbox:8882` (HTTP 401 = servidor lá),
   mas não `omni`.
2. **Key não bate.** O Omni usa `OMNI_API_KEY` do env como key primária **se setado**, senão gera
   um `omni_sk_…` por start (`packages/api/src/services/api-keys.ts`). No `.env` o `OMNI_API_KEY`
   está **vazio** → o backend manda key vazia → **HTTP 401** no `resolve_canonical` → cai no match
   direto → LID não acha.
3. O backend/worker precisam estar na `khal-wanet` (rede que alcança o Omni do sandbox).

## 2. Objetivo

Fazer a resolução da SPEC-015 **disparar** no sandbox: o agente reconhece o cliente que liga por
LID **sem** re-seed. **Sem** mudar o algoritmo da SPEC-015.

## 3. Escopo

### Key fixa (env, sem código novo)
- `.env.example` / `.env`: `OMNI_API_KEY` passa a ter um **valor fixo** (não vazio).
- `sandbox/compose.sandbox.yml`: o serviço `sandbox` ganha `OMNI_API_KEY: ${OMNI_API_KEY}` — a Omni
  API (rodada por `sandbox-up.sh`) lê `process.env.OMNI_API_KEY` e a usa como key primária. Backend
  e Omni passam a usar **a mesma** key → `resolve_canonical` autentica.

### Rede / alias
- `sandbox/compose.sandbox.yml`: o `sandbox` ganha o **alias `omni`** na `khal-wanet`, e
  `backend`+`worker` entram na `khal-wanet`. `make sandbox-up` cria a rede e recria os 3.

**Trade-off de isolamento (decisão consciente — ADR-0006):** a Omni API roda **dentro** do
container do `sandbox`. Para o backend alcançá-la, backend e sandbox **precisam** compartilhar uma
rede (`khal-wanet`) — logo existe a rota L3 `backend↔sandbox`. **É a mesma rota que o proativo
(SPEC-009) já exige** (envio backend→Omni); esta SPEC não introduz coupling novo, só o torna
explícito. O **isolamento forte é o do AGENTE, via tool-scoping** (allow só `mcp__luz-do-vale__*`
+ `Bash(omni:*)`; deny `WebFetch`/`WebSearch`/`Bash` geral): o Claude Code **não tem como** emitir
requisição de rede arbitrária, então não alcança o backend pela `khal-wanet` — só pelo MCP. O
checo de rede "sandbox→backend = 000" da §6.0 deixa de valer (passa a ser alcançável em L3); a
garantia que permanece é a do agente (tool-scoping) + os guardrails determinísticos no MCP/código.

### Remoção do remendo
- `make sandbox-reseed` e `sandbox/reseed.sh`: removidos. RUNBOOK §6.4 vira "resolução automática
  (SPEC-015) — o LID resolve sozinho", e o fluxo §6 perde o passo de reseed.

## 4. Fora de escopo
- Mudar o algoritmo da SPEC-015 (correto e testado).
- Persistir o mapeamento LID↔telefone localmente (a resolução on-demand no Omni basta; SPEC-015 §4
  já deixou cache como follow-up).
- Rotacionar/secret-manage a `OMNI_API_KEY` (demo: valor fixo no `.env` gitignored).

## 5. Plano TDD

1. **Regressão (SPEC-015, unit/integration):** os testes de `resolve_canonical` (MockTransport:
   `externalId@lid` → `canonicalId`) e de `find_customer_by_phone` (acha via LID→Omni, tolera o nono
   dígito) seguem **verdes** — esta SPEC não toca o algoritmo.
2. **Config (unit):** a Omni API usa `OMNI_API_KEY` do env quando setado (coberto pelo Omni;
   documentamos a premissa). Backend e sandbox lêem o **mesmo** `OMNI_API_KEY`.
3. **E2E ao vivo (verificação manual, registrada):** seed pelo **telefone real** (`.env`, sem
   reseed) → mensagem do cliente por LID → `find_customer_by_phone(LID)` resolve o titular →
   resposta com dados reais. Provado com `docker logs khal-mcp` (tool-calls) + o turno do agente.
4. **Remoção:** suíte verde sem `reseed.sh`; o §6 sem o passo entrega a resposta.

## 6. Critérios de aceite

- `find_customer_by_phone(<LID>)` acha o titular **sem** `sandbox-reseed` (E2E ao vivo).
- `make sandbox-reseed` e `sandbox/reseed.sh` removidos; RUNBOOK §6 sem o passo; o fluxo segue followable.
- Backend e Omni compartilham `OMNI_API_KEY` (env); `omni` resolve; backend/worker na `khal-wanet`.
- **Isolamento do AGENTE preservado** (tool-scoping: o Claude Code não alcança o negócio fora do
  MCP). A rota L3 backend↔sandbox via `khal-wanet` é aceita e documentada (a mesma do proativo,
  SPEC-009); o check de rede "sandbox→backend=000" da §6.0 é atualizado para refletir isso.
- unit+integration+lint/typecheck verdes; regressão da SPEC-015 intacta.
