# SPEC-009 - Notificações proativas determinísticas (eventos utilitycx.*)

- Status: Approved (2026-05-30) — PR #15
- Versao alvo: 1.0.0 (fecha o escopo do desafio)
- ADRs: ADR-0005 (eventos determinIsticos sem LLM -> memoria). Sem ADR novo.

## 1. Problema

Acoes do operador (baixa de pagamento, abrir/encerrar interrupcao) devem **notificar o
cliente no WhatsApp** e **atualizar o que o agente sabe**, **sem LLM** (conteudo canonico —
token optimization, ADR-0005). Hoje a `conversation_memory` existe (tabela + service), mas
**nao ha** publicacao/consumo de eventos nem disparo proativo, e o console nao expoe a acao.

## 2. Objetivo

Console do operador dispara um **evento de dominio** (`pagamento`/`outage`) -> publicado no
**NATS** (`utilitycx.*`, broker do Omni) -> **worker determinIstico** consome, envia a
**mensagem canonica** (template, sem LLM) via REST do Omni e **grava em `conversation_memory`**.
No proximo turno o agente le o contexto (ex.: "fatura paga", "luz voltou") sem reprocessar.

### Decisoes de arquitetura (pinadas; ADR-0005)
- **`EventBusPort`** (publish/subscribe) + adapter **NATS** — desacopla o broker.
- **`OmniSenderPort`** (envio de texto) + adapter **httpx** (REST do Omni) — no MVP, best-effort
  (loga se o Omni nao estiver acessivel); a memoria e gravada de qualquer forma (auditavel).
- **`ProactiveService`**: `disparar(evento)` (publica) e `processar(evento)` (render + send +
  memoria). Render **determinIstico** por template; **sem LLM** no caminho.
- **Worker** (`python -m src.infrastructure.events.worker`): assina `utilitycx.>` -> `processar`.
- **Console**: card "Notificacoes proativas" no workspace do cliente dispara o evento (REST).

## 3. Escopo

### Back
- **Dominio** `notifications`: `EventoCX` (tipo, subtipo, telefone, nome, idempotency_key,
  dados; `chat_id` derivado do telefone) e `render_notificacao(evento) -> str` (templates
  canonicos por tipo/subtipo).
- **Ports**: `EventBus.publish(subject, payload)`, `OmniSender.send_text(chat_id, texto)`.
- **Application** `ProactiveService`: `disparar` (publica em `utilitycx.<tipo>`; a acao de
  dominio que muta o estado — baixa de fatura / abrir-encerrar interrupcao — entra via SPEC-010
  antes da publicacao), `processar` (render + send + `conversation_memory`), `candidatos(phone)`
  (faturas em aberto -> pagamento; interrupcao no bairro -> outage).
- **Infra**: `NatsEventBus`, `HttpxOmniSender`, `events/worker.py` (subscriber).
- **REST** `/api/proactive`: `GET /candidates?phone=`, `POST /events`.
- **Compose**: servico `nats` + `notifications-worker` (mesma imagem, entrypoint do worker).

### Front (console)
- `ui/src/lib/api.ts`: tipos + `getProactiveCandidates`, `postProactiveEvent`.
- `ui/src/sections/ProactiveSection.tsx`: card no `CustomerWorkspace` — lista candidatos
  (faturas em aberto, interrupcao no bairro), botoes "Avisar baixa de pagamento" /
  "Avisar status da interrupcao", e mostra a **mensagem determinIstica** enviada + gravada.

## 4. Templates determinISticos (sem LLM)

- **pagamento.confirmado**: "Oi, {nome}! ✅ Confirmamos o pagamento da sua fatura de {mes}
  no valor de {valor}. Obrigado! 🙌"
- **pagamento.vencida**: "Oi, {nome}! ⚠️ Sua fatura de {mes} no valor de {valor} está
  *vencida*. Para evitar juros e multa por atraso (e risco de suspensão do fornecimento),
  pague pelo PIX ou boleto o quanto antes. Precisa da 2ª via? É só pedir por aqui. 🙂"
- **outage.aberta**: "{nome}, identificamos uma interrupção de energia no seu bairro
  ({bairro}). Nossa equipe já foi acionada. Previsão de retorno: {previsao}. Pode acompanhar
  por aqui." (o trecho de previsão é omitido quando não há previsão)
- **outage.encerrada**: "{nome}, boa notícia: o fornecimento no seu bairro ({bairro}) foi
  normalizado. ⚡ Se ainda estiver sem energia, é só me avisar."

Cada evento grava em `conversation_memory`: chave `proativo.{tipo}.{subtipo}`, valor
`{texto, em, dados, idempotency_key}`.

## 5. Fora de escopo

- Geracao do conteudo por LLM (proibido por ADR-0005 — determinIstico).
- Envio real ao WhatsApp sem o runtime do Omni (no sandbox o `OmniSender` aponta para o Omni;
  no deliverable e best-effort + memoria auditavel).
- Agendamento/cron de notificacoes (disparo e manual pelo operador no MVP).

## 6. Plano TDD (red -> green -> refactor)

1. **Dominio**: `render_notificacao` por tipo/subtipo (determinIstico, sem LLM). (unit)
2. **Service**: `processar` (render + send + memoria via fakes; assert idempotente por key),
   `candidatos`, `disparar` (publica no bus). (unit)
3. **EventBus NATS**: publish/subscribe round-trip. (integration)
4. **REST**: `GET /candidates`, `POST /events` (publica + 202). (api)
5. **Worker**: consome `utilitycx.>` -> `processar` (com fakes). (unit)
6. **Front**: `ProactiveSection` consome a API; build do console verde.
7. **Docs/compose**: nats + worker, README, env.example.

## 7. Riscos e mitigacao

- **Acoplamento ao NATS**: mitigado por `EventBusPort` (troca de broker sem mexer no caso de uso).
- **Omni indisponivel** (deliverable sem sandbox): `OmniSender` best-effort + memoria sempre
  gravada (a notificacao fica auditavel; no sandbox o envio real ocorre).
- **Duplicidade**: `idempotency_key` por evento; `processar` idempotente na memoria.

## 8. Criterios de aceite

- Operador dispara, pelo console, "baixa de pagamento" e "status de interrupcao"; o cliente
  recebe a **mensagem canonica** (sem LLM) e o evento fica em `conversation_memory`.
- Worker consome `utilitycx.*` do NATS e processa deterministicamente.
- unit + integration + api + lint/typecheck verdes; build do console verde.
