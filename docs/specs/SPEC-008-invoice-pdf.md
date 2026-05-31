# SPEC-008 - generate_invoice_pdf (render realista + MinIO + gateway)

- Status: Approved (2026-05-30)
- Versao alvo: 0.9.0 (fecha as 9 tools MCP)
- ADRs: **ADR-0009 (novo)** — object storage (MinIO) + render WeasyPrint + presigned.
  Mantem ADR-0003 (midia via tool action). Hexagonal/DDD (ADR-0001).

## 1. Problema

A 9a tool-alvo, `generate_invoice_pdf`, e um **stub `501`** (`billing.py`). Falta gerar o
**PDF realista** da fatura (A4, com **PIX QR**, **codigo de barras do boleto**, tarifa,
juros/multa, bandeira) e **persisti-lo** para nao re-renderizar a cada pedido, expondo a
URL pelo **gateway** e, opcionalmente, um **link pre-assinado com expiracao**.

## 2. Objetivo

Renderizar a fatura uma vez, **armazenar a copia no MinIO** (idempotente por chave), e
devolver a **URL** (estavel, via proxy do gateway) — com **opcao de link pre-assinado**
(TTL) que **regera apenas o link**, nunca o PDF. A tool MCP expoe isso (MCP-over-REST,
SPEC-003); o envio por **`POST /messages/send/media`** do Omni segue o ADR-0003 (runtime).

### Decisoes de arquitetura (pinadas; ver ADR-0009)
- **Render**: HTML+CSS -> **WeasyPrint** (A4), com **QR PIX** (`qrcode`) e **codigo de barras**
  do boleto (`python-barcode`, Interleaved 2of5) embutidos como PNG base64. HTML/CSS da o
  visual de uma conta de energia real (cabecalho da distribuidora, blocos, tabela de
  tributos, historico de consumo).
- **Storage**: **MinIO** (S3-compativel) atras de `ObjectStoragePort`. Chave determinIstica
  `invoices/{fatura_id}.pdf`. **Nao regera**: se o objeto existe, devolve a copia.
- **URL**: (a) **estavel** via **proxy do gateway** (`/files/invoices/{id}.pdf` -> MinIO);
  (b) **pre-assinada** com `expires` (TTL) — regenerada a cada pedido, o PDF permanece.
- **Hexagonal**: `InvoicePdfRenderer` (port) + `WeasyPrintInvoiceRenderer` (infra);
  `ObjectStoragePort` + `MinioObjectStorage`; `InvoiceDocumentService` (application).

## 3. Escopo

- **Domínio** `billing`: `FaturaDetalhada` (titular + UC + fatura + historico) e o calculo
  da composicao tarifaria/encargos (energia, bandeira, tributos, CIP) e de **juros/multa**
  pos-vencimento — deterministico, derivado do `valor`/`consumo`/`status`/`vencimento`.
- **Ports** (application): `InvoicePdfRenderer.render(detalhe) -> bytes`,
  `ObjectStoragePort.put/exists/url/presigned_url`.
- **Infra**: `WeasyPrintInvoiceRenderer` (template Jinja2 + CSS + QR + barcode);
  `MinioObjectStorage` (SDK `minio`); bucket `faturas` criado no boot.
- **Application** `InvoiceDocumentService.obter_ou_gerar(fatura_id, presign, expires)`:
  resolve `FaturaDetalhada`, gera+armazena se ausente, devolve `{url, presigned, expires_at}`.
- **REST**: `GET /api/invoices/{id}/pdf?presigned=&expires=` -> JSON com a URL (substitui o
  stub 501). Opcional `GET .../pdf/raw` para stream direto (debug).
- **Gateway** (nginx): `location /files/ { proxy_pass http://minio/faturas/; }`.
- **Compose**: servico `minio` (+ `mc` para criar o bucket); env no backend/mcp.
- **MCP**: `generate_invoice_pdf(phone)` -> resolve a fatura atual do titular -> REST ->
  devolve a URL. (Envio por midia do Omni: ADR-0003, runtime.)

## 4. Conteudo da fatura (realista, A4)

Cabecalho **Luz do Vale Distribuidora de Energia S.A.** (CNPJ ficticio) + logo; bloco do
cliente (nome, CPF mascarado, endereco, UC, classe/subgrupo); mes de referencia, emissao,
**vencimento**; **historico de consumo** (ultimos meses, mini-grafico de barras);
**composicao**: Energia (TE+TUSD), **Bandeira `<cor>` (R$/100 kWh x consumo)**, ICMS,
PIS/COFINS, **CIP/Iluminacao Publica**; **total**; clausula de **multa 2% + juros 1% a.m. +
correcao** apos o vencimento (com o valor atualizado se `vencida`); **PIX** (QR + copia e
cola) e **boleto** (codigo de barras + linha digitavel). Marca d'agua por `status`
(`EM ABERTO`/`VENCIDA`/`PAGA`).

## 5. Fora de escopo

- Assinatura digital/validade fiscal (e demo).
- Envio real por Omni `send/media` (ADR-0003 / runtime do sandbox; aqui a tool devolve a URL).
- Versionar PDFs no git (vivem no MinIO; bucket efemero recriavel).

## 6. Plano TDD (red -> green -> refactor)

1. **Dominio**: composicao tarifaria + juros/multa pos-vencimento (deterministico). (unit)
2. **Renderer**: `WeasyPrintInvoiceRenderer` produz PDF (assina `%PDF`, A4, contem QR/barcode
   embutidos). (unit, sem rede)
3. **Storage**: `MinioObjectStorage` put/exists/presigned contra MinIO efemero. (integration)
4. **Service**: `obter_ou_gerar` — 1a vez gera+armazena; 2a vez **nao** re-renderiza
   (renderer mockado conta as chamadas); presign regera so o link. (unit)
5. **REST**: `GET /invoices/{id}/pdf` devolve URL/expires; 404 fatura inexistente. (api)
6. **MCP**: tool `generate_invoice_pdf` (wrapper REST) + contrato. (unit)
7. **Docs/ADR**: ADR-0009, README, compose, gateway.

## 7. Riscos e mitigacao

- **WeasyPrint exige libs de sistema** (pango/cairo): adicionadas a imagem do backend/mcp.
- **MinIO presigned aponta para o host interno**: a URL **estavel** usa o gateway (`/files`);
  o presigned e para acesso direto/temporario (documentado).
- **Re-render acidental**: chave deterministica + `exists()` antes de renderizar; teste cobre.

## 8. Criterios de aceite

- `GET /api/invoices/{id}/pdf` devolve URL **proxyada pelo gateway**; o PDF abre como A4 com
  PIX QR + codigo de barras + tarifa/juros/multa/bandeira.
- **Idempotente**: 2o pedido **nao** re-renderiza (copia do MinIO).
- **Presigned** opcional com `expires`: regenera so o link; o objeto permanece.
- Tool MCP `generate_invoice_pdf` operacional. unit+integration+api+lint+typecheck verdes.
