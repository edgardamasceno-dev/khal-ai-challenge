# ADR-0010 - Rota direta de mídia opt-in (anexo no WhatsApp vs egress isolado)

- Status: Accepted
- Data: 2026-05-31
- SPEC: SPEC-019 (estende SPEC-017; ADR-0003 = PDF sai por send/media; ADR-0006 = sandbox)

## Context

A 2ª via deve chegar como **anexo PDF** no WhatsApp (ADR-0003, SPEC-017). O envio (`send/media`
base64) e o link foram implementados, mas o **upload do anexo aos CDNs de mídia do WhatsApp
nunca completava** sob a sandbox isolada (ADR-0006: o `egress-proxy`/tinyproxy é a única rota
de saída, com allowlist — doc 07).

Causa-raiz (confirmada no container, não suposição): o upload de mídia do Baileys usa
`fetch(url, { body: webStream, duplex: 'half' })` — POST com **streaming**. O **`fetch` nativo
do Bun não tuneliza upload streaming através de um proxy HTTP `CONNECT`**. Evidência:

| Caminho | Resultado |
|---|---|
| Bun `fetch` **via proxy** + stream | falha (socket fechado / timeout ~40s) |
| `undici` `ProxyAgent` via proxy + stream | 200 — **mas** o Baileys usa o `fetch` built-in do Bun, não substituível por `setGlobalDispatcher`/monkey-patch |
| Bun `fetch` **direto** (sem proxy) + stream | **200** |

O bloqueio não é o WhatsApp nem o tinyproxy — é o par `Bun fetch + CONNECT + streaming`.
Sem o proxy no caminho do upload, a mídia sobe.

## Decision

Habilitar a rota direta aos CDNs de mídia de forma **opt-in**, preservando o default isolado:

1. **`NO_PROXY` += `mmg.whatsapp.net,.cdn.whatsapp.net,.fna.whatsapp.net`** no env do sandbox.
   Faz só o tráfego de mídia evitar o proxy. **Inócuo sem internet direta** — sem rota direta,
   o Omni tenta os CDNs e falha, e o **link** no texto entrega a 2ª via (fallback da SPEC-017).
2. **`sandbox/enable-media.sh`** (opt-in): conecta o sandbox a uma rede com saída NAT
   (`bridge`) só quando se quer o anexo em demo. **`disable-media.sh`** reverte. O
   `compose.sandbox.yml` **versionado não muda o default** — segue só `mcpnet` + `egressnet`
   (ambas `internal`), egress-proxy como única rota.

Por que não "só os CDNs" no nível de rede: exigiria firewall por IP/AS, e os IPs do Meta CDN
variam (`media-*.cdn`, `*.fna`, ranges rotativos) — inviável de forma estável. A rota direta
abre a **interface** de rede; o `NO_PROXY` restrito garante que o tráfego *intencional* do Omni
(WebSocket, API) siga pelo proxy allowlist — só a mídia vai direto.

**Nota (anexo em base64, não URL do MinIO):** o PDF anexo trafega como **base64** no payload do
`send/media` (`omni_sender.py::send_document`), e **não** como URL do MinIO. O Omni roda na
sandbox e **não alcança o MinIO local**, então o documento é re-renderizado e embutido em base64
(`services.py::enviar_2a_via`). O **link público** (gateway `/files/`) vai apenas no **texto** — é
ele que aponta para o MinIO; o anexo carrega os bytes inline.

### Nota: `khal-wanet` (WSS) vs `bridge` (upload de mídia)

O RUNBOOK 6.0 já conecta o sandbox a `khal-wanet` (rede não-interna) porque o **WebSocket** do
Baileys (`wss://web.whatsapp.com`) não honra `HTTP_PROXY` — isso já dá internet ao processo
Baileys (curl/WSS funcionam por ela). Mas o **upload de mídia** usa o `fetch` do Bun com
streaming e, observado empiricamente, **só completa pela `bridge`** (MTU 65535 / rota default),
não pela `khal-wanet` (MTU 1500) — onde o `fetch` dá "socket closed" embora curl/WSS funcionem.
Por isso `enable-media.sh` usa a `bridge` (testado: `send/media` → 201 em ~1.4s). A causa fina
(MTU vs rota default do multi-homing) não foi isolada; o efeito é reproduzível e o script fixa o
caminho que funciona.

## Consequences

Positivas:
- O anexo PDF sobe de fato (`send/media` → 201 em ~2-3s; antes: timeout 40s que congelava o
  turno do agente e derrubava `create_ticket`).
- O default da entrega mantém o isolamento forte do doc 07/ADR-0006 — o avaliador escolhe a
  postura; a rota de mídia é explícita, reversível e documentada.
- A causa-raiz fica registrada (Bun `fetch` + proxy CONNECT + streaming), não folclore.

Negativas / trade-off:
- Com o opt-in ativo, a sandbox ganha uma interface com saída de internet (NAT): código
  não-confiável *poderia* exfiltrar por ela ignorando o proxy. Mitigação: opt-in (desligado por
  default), `NO_PROXY` restrito, e a recomendação de só ligar em demo controlada, sem
  credenciais reais (a sandbox já não tem segredos — ADR-0006/0007).
- Dois modos de operação (isolado vs mídia) a documentar no RUNBOOK.

## Alternatives

- **Afrouxar o default do compose** (sandbox sempre com internet): anexo sempre funciona, mas
  a entrega versionada perde a postura de isolamento — preterido (default deve ser o seguro).
- **Patch no Baileys (`node_modules`) forçando `undici ProxyAgent`** no `uploadWithFetch`:
  tentado e **não funcionou** (o `import('undici')` no contexto do pacote + `dispatcher` no
  `fetch` do Baileys deram timeout); além de frágil e dentro da fronteira não-confiável (doc 07).
- **Trocar o tinyproxy por proxy que tunelize streaming** (squid/undici-proxy): incerto e
  amplia a superfície do componente de borda; preterido.
- **Só link, sem anexo**: cumpre o ADR-0003 parcialmente (link é confiável), mas não entrega o
  "documento anexo" pedido; a rota opt-in fecha o requisito quando desejado.
