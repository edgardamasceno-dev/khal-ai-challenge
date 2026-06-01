# SPEC-019 - Egress de mídia opt-in (anexo PDF no WhatsApp)

- Status: Approved (2026-05-31)
- Versao alvo: 1.4.2 (o anexo da 2ª via realmente sobe aos CDNs do WhatsApp)
- ADRs: **ADR-0010** (rota direta de mídia opt-in). Estende a SPEC-017 (que entregou o
  `send_document`/`/send`, mas o upload falhava no ambiente isolado).

## 1. Problema

A SPEC-017 implementou o envio do anexo (`send/media` base64) e o link no texto. O **link**
sempre chega, mas o **anexo nunca subia**: o upload do Baileys aos CDNs de mídia
(`mmg.whatsapp.net`, `*.cdn.whatsapp.net`) falhava sob a sandbox isolada (egress só via
`egress-proxy`, doc 07/ADR-0006). Sintoma: `send/media` travava ~40s e o agente "dizia que
enviou" sem anexo — chegando a congelar a sessão do Genie e derrubar outras tools
(`create_ticket`) por o timeout longo bloquear o turno.

### Causa-raiz (investigada nos serviços/banco)

O upload de mídia do Baileys usa `fetch(url, { body: webStream, duplex: 'half' })` (streaming).
O **`fetch` nativo do Bun não tuneliza upload com streaming através de um proxy HTTP
`CONNECT`** (o `tinyproxy` do egress). Confirmado empiricamente no container:

- `fetch` **via proxy** + stream → falha (socket fechado / timeout).
- `undici` `ProxyAgent` via proxy + stream → 200 (mas o Baileys usa o `fetch` built-in do
  Bun, não alcançável por `setGlobalDispatcher`/monkey-patch — todas as tentativas falharam).
- `fetch` **direto** (sem proxy) + stream → **200**.

Ou seja: o bloqueio não é o WhatsApp nem o tinyproxy — é o par **Bun `fetch` + `CONNECT` +
streaming**. Sem o proxy no caminho, o upload funciona.

## 2. Objetivo

Permitir que o anexo PDF suba de fato, **sem afrouxar o default da entrega**: o
`compose.sandbox.yml` versionado mantém o isolamento forte (egress-proxy = única rota,
ADR-0006). A rota direta aos CDNs de mídia é **opt-in**, explícita e documentada.

## 3. Decisões

- **`NO_PROXY` += CDNs de mídia** no env do sandbox: `mmg.whatsapp.net,.cdn.whatsapp.net,
  .fna.whatsapp.net`. **Inócuo sem internet direta** (o Omni tenta direto, falha, o link
  cobre); habilita o anexo quando há rota direta. Não enfraquece o default.
- **`sandbox/enable-media.sh` (opt-in)**: conecta o sandbox a uma rede com saída de internet
  (`bridge`/NAT) só para demos de mídia. Idempotente. Reversível por `disable-media.sh`.
- **Default seguro intacto**: sem rodar o script, a sandbox segue só com `egress-proxy`
  (allowlist). O anexo simplesmente não sobe e o **link** entrega a 2ª via — exatamente o
  fallback best-effort da SPEC-017.
- **Trade-off documentado em ADR-0010**: a rota direta abre a interface de rede (não só os
  CDNs — firewall por IP é inviável porque os IPs do Meta variam). Mitigação: `NO_PROXY`
  restrito, então o tráfego *intencional* do Omni segue pelo proxy allowlist; só a mídia vai
  direto. Opt-in: o avaliador escolhe a postura.

## 4. Escopo

- `sandbox/compose.sandbox.yml`: `NO_PROXY` do `sandbox` += CDNs de mídia (ativo; inócuo sem rota direta).
- `sandbox/enable-media.sh` + `sandbox/disable-media.sh`: liga/desliga a rota direta (opt-in).
- `sandbox/RUNBOOK.md` + `README`: como e quando usar; o trade-off.
- `docs/adrs/ADR-0010-media-egress-optin.md`.
- `HttpxOmniSender.media_timeout`: 6s → 12s (o upload real leva ~2-3s; margem p/ PDFs maiores).

## 5. Fora de escopo

- Firewall por IP/AS para "só os CDNs" no nível de rede (IPs do Meta variam; inviável estável).
- Patch no Baileys/`node_modules` (tentado: forçar `undici ProxyAgent` no `uploadWithFetch`
  não funcionou; descartado por ser frágil e fora da fronteira confiável — doc 07).
- Trocar o `tinyproxy` por outro proxy que tunelize streaming (incerto; mais superfície).

## 6. Plano TDD

1. **Adapter** (unit): `HttpxOmniSender(media_timeout=12.0)` default; corpo do `send_document`
   inalterado (regressão da SPEC-017 segue verde).
2. **Script** (bash, validação manual documentada): `enable-media.sh` é idempotente
   (reexecução não falha) e `disable-media.sh` reverte.
3. **Validação E2E manual** (registrada na SPEC): `POST /invoices/{id}/send` do titular real →
   `enviado_anexo: true`, `send/media` → 201 em ~2-3s; sem o script → `enviado_link: true`,
   `enviado_anexo: false` (fallback), default isolado preservado.
4. **Regressão**: unit + api + lint/typecheck verdes.

## 7. Critérios de aceite

- Default (sem opt-in): sandbox só via egress-proxy; 2ª via chega pelo **link** (anexo false).
- Com `enable-media.sh`: 2ª via chega como **anexo PDF** + link; `send/media` 201 em segundos.
- `disable-media.sh` restaura o isolamento.
- ADR-0010 registra o trade-off e as alternativas rejeitadas; RUNBOOK atualizado.
- unit + api + lint/typecheck verdes.

## 8. Validação E2E (executada — 2026-05-31)

- `fetch` direto + stream a `mmg.whatsapp.net` no container → **200** (proxy era o bloqueio).
- Omni reiniciado com `NO_PROXY` += CDNs + sandbox na `bridge`:
  - `POST /api/v2/messages/send/media` (PDF base64) → **201 em 2.3s** (antes: timeout 40s).
  - `POST /invoices/{id}/send` (titular real, fluxo completo) → `enviado_anexo: true` em 6.9s
    (render WeasyPrint + link + upload).
