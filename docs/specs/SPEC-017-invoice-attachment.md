# SPEC-017 - 2ª via como anexo no WhatsApp (+ link)

- Status: Approved (2026-05-30)
- Versao alvo: 1.4.1 (a 2ª via sai como documento anexo, não só URL)
- ADRs: ADR-0003 (PDF sai por send/media, nunca pelo reply de texto). Sem ADR novo.

## 1. Problema

A tool `generate_invoice_pdf` gera o PDF, persiste no MinIO e devolve a **URL** — mas
**nunca envia o anexo** no WhatsApp. O ADR-0003 previa `POST /messages/send/media`, mas
nunca foi implementado. O agente "diz que enviou" (manda a URL no texto, na melhor das
hipóteses) e o cliente não recebe a fatura.

## 2. Objetivo

A 2ª via chega ao cliente como **documento PDF anexo** no WhatsApp (ADR-0003) **e** com
o **link** (pré-assinado) no texto como redundância. Determinístico, via tool action.

## 3. Decisões

- **Envio pelo backend** (tem o Omni wired e o PDF em bytes). A tool chama um endpoint;
  o backend renderiza, envia o anexo e o link.
- **base64**, não URL: o Omni baixa a URL *server-side* e não alcança o `localhost`/MinIO;
  mandar o PDF em base64 (`POST /api/v2/messages/send/media type=document`) é robusto.
- **Destino = telefone cadastrado do titular** dono da fatura (resolvido server-side),
  não o LID. O `check-number` do Omni resolve o JID (com/sem 9). Guardrail: envia só ao
  titular da fatura.

## 4. Escopo

### Back
- `OmniSender` += `send_document(chat_id, conteudo, filename, caption)` — adapter
  `HttpxOmniSender` resolve o JID (check-number) e faz `send/media` (base64). Best-effort.
- `InvoiceDocumentService.enviar_2a_via(fatura_id)`: resolve titular dono, garante o PDF
  (MinIO) + link pré-assinado, envia o **anexo** ao telefone do titular e o **link** no
  texto. Devolve `{enviado, enviado_link, enviado_anexo, mes_referencia, status, url}`.
- REST: `POST /invoices/{fatura_id}/send` -> envia. (`GET .../pdf` segue para o console.)

### MCP
- `generate_invoice_pdf(phone)` passa a **enviar** (chama `/send`) e reporta `enviado`.

## 5. Fora de escopo

- Reenvio/expiração de link configurável (usa o presign atual).
- Anexar boleto separado (o PDF já traz boleto/PIX — SPEC-008).

## 6. Plano TDD

1. **Adapter** (unit, mock): `send_document` monta o corpo base64 e faz POST; falha -> False.
2. **Service** (unit, fakes): `enviar_2a_via` renderiza, envia anexo + link, devolve url;
   fatura/titular inexistente -> erro.
3. **REST** (api): `POST /invoices/{id}/send` devolve `enviado` + url.
4. **Tool** (unit): `generate_invoice_pdf` chama o send e reporta `enviado`.
5. **Regressão**: suite verde.

## 7. Critérios de aceite

- Pedir 2ª via -> cliente recebe o PDF **anexo** no WhatsApp + o link no texto.
- O destino é o telefone do titular (não o LID); best-effort sem Omni.
- unit+api+lint/typecheck verdes.
