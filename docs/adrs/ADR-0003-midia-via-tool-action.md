# ADR-0003 - Envio de midia (PDF) como acao de ferramenta

- Status: Accepted
- Data: 2026-05-30

## Context

A segunda via de fatura deve chegar como **PDF no WhatsApp**. Auditoria do codigo do Omni (`libs/omni`) mostrou:

- Envio de documento e suportado: `senders/media.ts` (`buildDocumentContent`), `POST /api/v2/messages/send/media` (`type: 'document'`, `url` ou `base64`, `filename`, `caption`), SDK `messages.sendMedia`, CLI `omni send --media`.
- O canal de reply do agente (`omni.reply.{instance}.{chat}`) e **texto-puro**: o `NatsReplyMessage` so tem `content: string`, sem campo de midia.

Logo, o PDF nao pode voltar pela resposta normal (texto) do agente.

## Decision

Modelar o envio de PDF como **acao de ferramenta**: a tool `generate_invoice_pdf` renderiza o documento (WeasyPrint) e chama `POST /api/v2/messages/send/media` (type=document, base64) via adapter de canal, devolvendo o protocolo ao agente. O agente entao responde em **texto** ("enviei sua segunda via"). Notificacoes proativas (outage, pagamento) seguem o mesmo principio: outbound por REST do Omni, fora do canal de reply.

## Consequences

Positivas:
- Funciona com a arquitetura real do Omni (sem hacks no reply).
- Demonstra entendimento da estratificacao de mensagens (inbound carrega `files[]`, reply e texto, midia sai por API autenticada).

Negativas:
- A camada de ferramentas precisa de credenciais do Omni (`OMNI_API_KEY`, `OMNI_INSTANCE_ID`). Mitigado por `.env` em sandbox e redacao em logs.

## Alternatives

- **Enviar PDF pelo reply do agente**: impossivel; reply e texto-puro.
- **Mandar link em vez de anexo**: pior UX e exige hospedagem publica do PDF.
