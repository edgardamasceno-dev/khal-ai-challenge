# Dicionario de dados

PostgreSQL. Nomes em snake_case. `Dinheiro` armazenado em centavos (inteiro). PII classificada na ultima coluna: `alta` (redigir sempre em logs), `media`, `nenhuma`.

## titulares

| Coluna | Tipo | Notas | PII |
| --- | --- | --- | --- |
| id | uuid PK | | nenhuma |
| nome | text | | media |
| cpf | char(11) | digito verificador valido, ficticio | alta |
| email | text | | media |
| telefone_principal | varchar(15) | E.164 sem '+' | alta |
| persona_key | text | rotulo do seed (ex.: ana.souza) | nenhuma |
| created_at | timestamptz | | nenhuma |

## unidades_consumidoras

| Coluna | Tipo | Notas | PII |
| --- | --- | --- | --- |
| id | uuid PK | | nenhuma |
| numero_uc | varchar(12) | identificador publico | media |
| titular_id | uuid FK -> titulares | | nenhuma |
| logradouro | text | | media |
| bairro | text | usado no match de outage | media |
| cidade | text | | nenhuma |
| uf | char(2) | | nenhuma |
| cep | char(8) | | media |
| classe | text | residencial/comercial/industrial/rural/poder_publico | nenhuma |
| subgrupo | varchar(4) | B1/B2/B3... | nenhuma |
| status | text | ativa/cortada | nenhuma |
| distribuidora | text | "Luz do Vale" | nenhuma |
| data_ligacao | date | | nenhuma |

## contratos

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| titular_id | uuid FK | |
| uc_id | uuid FK | |
| modalidade | text | convencional/branca |
| data_inicio | date | |
| status | text | ativo/encerrado |

## leituras

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| uc_id | uuid FK | |
| mes_referencia | char(7) | YYYY-MM |
| consumo_kwh | integer | |
| data_leitura | date | |

## faturas

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| uc_id | uuid FK | |
| mes_referencia | char(7) | YYYY-MM; unico por UC |
| consumo_kwh | integer | |
| valor_total_centavos | integer | |
| bandeira | text | verde/amarela/vermelha_p1/vermelha_p2 |
| vencimento | date | |
| status | text | paga/em_aberto/vencida |
| linha_digitavel | varchar(54) | ficticia |
| pix_copia_cola | text | ficticio |
| emitida_em | timestamptz | |

## pagamentos

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| fatura_id | uuid FK | |
| valor_centavos | integer | |
| data_pagamento | timestamptz | |
| meio | text | pix/boleto/cartao |
| idempotency_key | text unico | evita baixa duplicada |

## interrupcoes

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| bairro | text | match por bairro+cidade+uf |
| cidade | text | |
| uf | char(2) | |
| tipo | text | programada/nao_programada |
| causa | text | |
| inicio | timestamptz | |
| previsao_retorno | timestamptz | |
| status | text | ativa/encerrada |
| encerrada_em | timestamptz | null se ativa |

## chamados

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| protocolo | varchar(16) unico | gerado |
| titular_id | uuid FK | |
| uc_id | uuid FK | |
| tipo | text | falta_energia/religacao/segunda_via/titularidade/reclamacao |
| descricao | text | |
| status | text | aberto/em_andamento/resolvido/escalado |
| sla_horas | integer | por tipo |
| canal | text | whatsapp |
| aberto_em | timestamptz | |
| atualizado_em | timestamptz | |
| idempotency_key | text unico | evita chamado duplicado |

## handoff_queue

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| chamado_id | uuid FK | |
| remetente | text | id do chat (LID/telefone) p/ pausar/retomar a IA no Omni (SPEC-016) |
| motivo | text | |
| status | text | pendente/assumido/resolvido |
| operador | text | null ate assumido |
| criado_em | timestamptz | |

## conversation_memory

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| chat_id | text | id do chat no Omni/WhatsApp |
| titular_id | uuid FK null | resolvido apos identificacao |
| chave | text | ex.: ultima_uc, ultimo_protocolo, fatura_paga |
| valor | jsonb | |
| atualizado_em | timestamptz | |

## tool_call_audit

> Materializada (T3 / ADR-0012): ORM `ToolCallAuditORM` + sink atrás do port `ToolCallAuditSink`.
> O RECORDER do MCP (`src/interfaces/mcp/audit.py`) grava um registro por chamada de tool com
> input **mascarado** (telefone → sufixo de 4 dígitos; CPF nunca em claro), `result_status`,
> `latency_ms` e `error_code`. Persistência **best-effort** (falha de auditoria nunca derruba a
> tool) + log estruturado JSON por chamada.

| Coluna | Tipo | Notas |
| --- | --- | --- |
| id | uuid PK | |
| trace_id | text | propagado do payload do Omni |
| chat_id | text | |
| tool_name | text | |
| input_redacted | jsonb | PII redigida |
| result_status | text | ok/error/denied |
| latency_ms | integer | |
| error_code | text null | |
| created_at | timestamptz | |
