# Diagrama entidade-relacionamento

```mermaid
erDiagram
    TITULAR ||--o{ UNIDADE_CONSUMIDORA : possui
    TITULAR ||--o{ CONTRATO : assina
    UNIDADE_CONSUMIDORA ||--o{ CONTRATO : vinculada
    UNIDADE_CONSUMIDORA ||--o{ LEITURA : tem
    UNIDADE_CONSUMIDORA ||--o{ FATURA : gera
    FATURA ||--o{ PAGAMENTO : recebe
    TITULAR ||--o{ CHAMADO : abre
    UNIDADE_CONSUMIDORA ||--o{ CHAMADO : referente
    CHAMADO ||--o| HANDOFF_QUEUE : escala
    TITULAR ||--o{ CONVERSATION_MEMORY : contextualiza

    TITULAR {
        uuid id
        text nome
        char cpf
        varchar telefone_principal
        text persona_key
    }
    UNIDADE_CONSUMIDORA {
        uuid id
        varchar numero_uc
        text bairro
        text classe
        text status
    }
    FATURA {
        uuid id
        char mes_referencia
        integer valor_total_centavos
        text bandeira
        date vencimento
        text status
    }
    PAGAMENTO {
        uuid id
        integer valor_centavos
        text meio
        text idempotency_key
    }
    INTERRUPCAO {
        uuid id
        text bairro
        text tipo
        timestamptz previsao_retorno
        text status
    }
    CHAMADO {
        uuid id
        varchar protocolo
        text tipo
        text status
        integer sla_horas
    }
    HANDOFF_QUEUE {
        uuid id
        text motivo
        text status
        text operador
    }
    CONVERSATION_MEMORY {
        uuid id
        text chat_id
        text chave
        jsonb valor
    }
```

Nota: `INTERRUPCAO` nao tem FK direta para `UNIDADE_CONSUMIDORA`; a associacao e por **match de bairro + cidade + uf** no momento da consulta/notificacao (modelo realista de outage por area).
