# Linguagem ubiqua - dominio de energia

Vocabulario compartilhado entre codigo, docs, agente e KB. Os termos abaixo sao os nomes canonicos; use-os em entidades, ferramentas, mensagens e testes.

## Termos do dominio (energia)

| Termo (PT) | EN | Definicao |
| --- | --- | --- |
| Titular | Account holder | Pessoa responsavel pela conta. Identificado por CPF. |
| Unidade Consumidora (UC) | Metered point | Ponto de consumo com medidor, vinculado a um endereco. Um titular pode ter varias UCs. |
| Numero da UC / instalacao | Installation number | Identificador publico da UC. |
| Classe | Consumption class | residencial, comercial, industrial, rural, poder_publico. |
| Subgrupo tarifario | Tariff subgroup | B1 (residencial), B2 (rural), B3 (demais), etc. |
| Bandeira tarifaria | Tariff flag | verde, amarela, vermelha_p1, vermelha_p2. Custo adicional por kWh. |
| Leitura | Meter reading | Medicao mensal do consumo. |
| Consumo (kWh) | Consumption | Energia consumida no mes. |
| Fatura | Invoice | Conta mensal de uma UC. |
| Mes de referencia | Reference month | Mes faturado (YYYY-MM). |
| Vencimento | Due date | Data limite de pagamento. |
| Segunda via | Duplicate invoice | Reemissao da fatura (PDF). |
| Linha digitavel | Payment line | Codigo numerico de pagamento do boleto. |
| PIX copia e cola | PIX code | String PIX para pagamento. |
| Religacao | Reconnection | Restabelecimento apos pagamento de debito que gerou corte. |
| Corte | Disconnection | Suspensao por inadimplencia. |
| Interrupcao / falta de energia | Outage | Ausencia de fornecimento. |
| Interrupcao programada | Planned outage | Manutencao agendada. |
| Previsao de retorno | Estimated restoration | Horario previsto de restabelecimento. |
| Protocolo | Protocol | Numero do chamado. |
| Chamado | Ticket/case | Solicitacao registrada do cliente. |
| SLA | SLA | Prazo de atendimento por tipo de chamado. |
| Titularidade | Account ownership | Quem responde pela UC; pode ser transferida. |
| Distribuidora | Distribution utility | Concessionaria (ficticia: "Luz do Vale"). |
| Handoff | Handoff | Transferencia do atendimento para um humano. |

## Termos de arquitetura (DDD)

| Termo | Definicao |
| --- | --- |
| Bounded Context | Fronteira com modelo e linguagem proprios. |
| Aggregate | Cluster de objetos tratado como unidade transacional, com uma raiz. |
| Entity | Objeto com identidade propria ao longo do tempo. |
| Value Object | Objeto definido pelos atributos, sem identidade (ex.: CPF, Dinheiro). |
| Domain Event | Fato relevante do dominio (ex.: FaturaPaga). |
| Repository | Abstracao de persistencia de um aggregate. |
| Port / Adapter | Interface (port) e implementacao concreta (adapter) na borda. |

## Nota de consistencia

A distribuidora ficticia se chama **Luz do Vale**. Use este nome em faturas, KB e mensagens. Nenhum dado e real (ver `docs/security/pii-handling.md`).
