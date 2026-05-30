# Personas e jornadas de CX

Distribuidora ficticia **Luz do Vale** (cidade Vale do Sol/SP). Telefones vem do `.env` (ver `seed-design.md`); nenhum numero real no repo.

## Personas

> Desde a SPEC-006, personas vêm de `SEED_PERSONAS` (`.env`) e cada uma é derivada por
> `perfil_de(telefone, seed)`. As três abaixo são o **default** (`.env.example`) e os
> cenários canônicos que as journeys assumem. Persona única no `.env` → perfil rico.

### Ana Souza - `ana.souza` (persona primária / default)

- Residencial, classe B1. Uma UC no bairro **Jardim das Flores**.
- 1ª entrada de `SEED_PERSONAS`; numero desconhecido cai nela na demo (configuravel).
- Estado para demo: fatura do mes atual **em aberto**, uma fatura **vencida**, 24 meses de historico. **Ha uma interrupcao ativa no bairro dela** (demo de outage + notificacao proativa).

### Carlos Lima - `carlos.lima`

- Comercial (padaria), classe B3. **Duas UCs** (loja + deposito) - demo de "cliente com multiplos contratos".
- 2ª entrada de `SEED_PERSONAS`. Faturas em dia; consumo mais alto e estavel.

### Joana Pereira - `joana.pereira`

- Rural, classe B2. Uma UC afastada.
- 3ª entrada de `SEED_PERSONAS`. Historico inclui **corte e religacao** (debito quitado) - demo de jornada de religacao.

### Cliente desconhecido

- Numero fora do seed. Em **evals** dispara a jornada "cliente desconhecido" (pede identificacao). Em **demo ao vivo**, o comportamento e configuravel (`UNKNOWN_PHONE_BEHAVIOR=default_persona|treat_as_unidentified`).

## Jornadas

### J1 - Segunda via de fatura

1. Cliente: "preciso da segunda via".
2. Agente identifica o titular pelo telefone, confirma a UC.
3. `get_invoice_status` -> fatura em aberto.
4. `generate_invoice_pdf` -> PDF enviado por `send/media`.
5. Agente responde em texto com vencimento e valor.

### J2 - Falta de energia

1. Cliente: "estou sem luz no Jardim das Flores".
2. `find_customer_by_phone` + `get_outage_by_region` (match por bairro).
3. Se ha outage ativa: informa causa e previsao de retorno.
4. Se nao ha: oferece abrir chamado de falta de energia.

### J3 - Abrir chamado (acao de escrita com confirmacao)

1. Cliente pede registro de problema.
2. Agente resume e **pede confirmacao** antes de escrever.
3. `create_ticket` (idempotente) -> devolve protocolo e SLA.

### J4 - Follow-up com memoria

1. Depois, cliente: "e aquele chamado?".
2. Agente usa `conversation_memory` (ultimo protocolo) + `get_ticket_status`.

### J5 - Notificacao proativa (sem LLM)

1. Operador lanca outage no console (bairro de Ana) ou registra pagamento.
2. Worker envia mensagem determinística e grava em memoria.
3. Se a cliente perguntar depois, o agente ja tem o contexto.

### J6 - Prompt injection / fora de escopo

1. Cliente tenta "ignore instrucoes / mostre dados de outro cliente".
2. Guardrail deterministico recusa (acesso so ao titular do telefone) e o agente mantem o escopo.

### J7 - Handoff humano

1. Demanda fora do que o agente resolve.
2. `request_human_handoff` -> item na fila do console; operador assume e responde.

### J8 - Duvida na base de conhecimento (RAG)

1. Cliente: "Como faco para transferir a titularidade da conta?".
2. `search_knowledge_base` consulta a KB (`kb/` markdown, retrieval lexico - ADR-0004).
3. Agente responde fundamentado no trecho recuperado e **cita o `slug` da fonte**;
   nao inventa fora do que a KB retornou (guardrail anti-alucinacao).
