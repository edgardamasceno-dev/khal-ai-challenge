# ADR-0009 - Object storage (MinIO) + render WeasyPrint para faturas

- Status: Accepted
- Data: 2026-05-30
- SPEC: SPEC-008

## Context

A tool `generate_invoice_pdf` precisa de um PDF **realista** da fatura (A4, PIX QR, codigo
de barras, tarifa/juros) e de **persisti-lo**: re-renderizar a cada pedido e caro e nao
determinIstico em metadados. Precisamos expor a URL pelo **gateway** e, opcionalmente, um
**link pre-assinado** com expiracao — regerando apenas o link, nunca o PDF.

## Decision

- **Render**: HTML+CSS via **WeasyPrint** (A4). E a forma mais simples de obter um layout
  fiel a uma conta de energia (vs. desenhar com reportlab/fpdf). QR (PIX) com `qrcode` e
  codigo de barras (boleto) com `python-barcode`, embutidos como PNG base64 no HTML.
- **Storage**: **MinIO** (S3-compativel, self-hosted no compose) atras de um
  `ObjectStoragePort`. Chave determinIstica `invoices/{fatura_id}.pdf`; **idempotente**
  (`exists()` antes de renderizar -> armazena copia, nao regera).
- **Exposicao**: URL **estavel** via **proxy do gateway** (`/files/` -> bucket do MinIO);
  **link pre-assinado** (GET com TTL) como opcao — regenerado a cada pedido.

## Consequences

Positivas:
- PDF realista e reproduzivel; armazenado uma vez, servido muitas (sem re-render).
- Storage desacoplado por port (troca por S3/GCS sem mexer no caso de uso).
- Link estavel (gateway) para uso geral; presigned para acesso direto/temporario.

Negativas:
- WeasyPrint traz libs de sistema (pango/cairo) -> imagens do backend/mcp maiores.
- Mais um servico (MinIO) no compose. Aceitavel (S3-compativel, leve, padrao de mercado).

## Alternatives

- **reportlab/fpdf2** (sem libs de sistema): rejeitado para o MVP — muito mais codigo para o
  mesmo realismo; WeasyPrint via HTML/CSS e direto. Fica como alternativa se a imagem pesar.
- **Servir o PDF do proprio backend (sem object storage)**: rejeitado — re-render ou cache
  ad-hoc em disco do container (efemero, sem presigned). MinIO da copia + presigned padrao.
- **Guardar o PDF como bytea no Postgres**: rejeitado — incha o banco; object storage e o
  lugar certo para binarios, com URL/presigned nativos.
