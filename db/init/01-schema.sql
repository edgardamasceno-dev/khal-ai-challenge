-- Schema da "Luz do Vale" (distribuidora ficticia).
-- Espelha docs/domain/data-dictionary.md. Dinheiro em centavos (inteiro).
-- Roda uma unica vez, no primeiro boot do volume (docker-entrypoint-initdb.d).

SET client_min_messages = warning;

CREATE TABLE titulares (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nome               text NOT NULL,
    cpf                char(11) NOT NULL UNIQUE,
    email              text,
    telefone_principal varchar(15) NOT NULL,
    persona_key        text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE unidades_consumidoras (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_uc     varchar(12) NOT NULL UNIQUE,
    titular_id    uuid NOT NULL REFERENCES titulares(id),
    logradouro    text,
    bairro        text NOT NULL,
    cidade        text NOT NULL,
    uf            char(2) NOT NULL,
    cep           char(8),
    classe        text NOT NULL CHECK (classe IN
                    ('residencial','comercial','industrial','rural','poder_publico')),
    subgrupo      varchar(4),
    status        text NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa','cortada')),
    distribuidora text NOT NULL DEFAULT 'Luz do Vale',
    data_ligacao  date
);

CREATE TABLE contratos (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    titular_id  uuid NOT NULL REFERENCES titulares(id),
    uc_id       uuid NOT NULL REFERENCES unidades_consumidoras(id),
    modalidade  text NOT NULL CHECK (modalidade IN ('convencional','branca')),
    data_inicio date NOT NULL,
    status      text NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo','encerrado'))
);

CREATE TABLE leituras (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uc_id         uuid NOT NULL REFERENCES unidades_consumidoras(id),
    mes_referencia char(7) NOT NULL,                 -- YYYY-MM
    consumo_kwh   integer NOT NULL,
    data_leitura  date NOT NULL,
    UNIQUE (uc_id, mes_referencia)
);

CREATE TABLE faturas (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    uc_id                uuid NOT NULL REFERENCES unidades_consumidoras(id),
    mes_referencia       char(7) NOT NULL,            -- YYYY-MM, unico por UC
    consumo_kwh          integer NOT NULL,
    valor_total_centavos integer NOT NULL,
    bandeira             text NOT NULL CHECK (bandeira IN
                           ('verde','amarela','vermelha_p1','vermelha_p2')),
    vencimento           date NOT NULL,
    status               text NOT NULL CHECK (status IN ('paga','em_aberto','vencida')),
    linha_digitavel      varchar(54),
    pix_copia_cola       text,
    emitida_em           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (uc_id, mes_referencia)
);

CREATE TABLE pagamentos (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fatura_id       uuid NOT NULL REFERENCES faturas(id),
    valor_centavos  integer NOT NULL,
    data_pagamento  timestamptz NOT NULL DEFAULT now(),
    meio            text NOT NULL CHECK (meio IN ('pix','boleto','cartao')),
    idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE interrupcoes (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bairro           text NOT NULL,
    cidade           text NOT NULL,
    uf               char(2) NOT NULL,
    tipo             text NOT NULL CHECK (tipo IN ('programada','nao_programada')),
    causa            text,
    inicio           timestamptz NOT NULL,
    previsao_retorno timestamptz,
    status           text NOT NULL CHECK (status IN ('ativa','encerrada')),
    encerrada_em     timestamptz
);

CREATE TABLE chamados (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    protocolo       varchar(16) NOT NULL UNIQUE,
    titular_id      uuid NOT NULL REFERENCES titulares(id),
    uc_id           uuid REFERENCES unidades_consumidoras(id),
    tipo            text NOT NULL CHECK (tipo IN
                      ('falta_energia','religacao','segunda_via','titularidade','reclamacao')),
    descricao       text,
    status          text NOT NULL CHECK (status IN
                      ('aberto','em_andamento','resolvido','escalado')),
    sla_horas       integer NOT NULL,
    canal           text NOT NULL DEFAULT 'whatsapp',
    aberto_em       timestamptz NOT NULL DEFAULT now(),
    atualizado_em   timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE handoff_queue (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chamado_id uuid REFERENCES chamados(id),
    remetente  text,  -- id do chat (LID/telefone) p/ pausar/retomar a IA no Omni (SPEC-016)
    motivo     text,
    status     text NOT NULL DEFAULT 'pendente' CHECK (status IN
                 ('pendente','assumido','resolvido')),
    operador   text,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conversation_memory (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id       text NOT NULL,
    titular_id    uuid REFERENCES titulares(id),
    chave         text NOT NULL,
    valor         jsonb NOT NULL,
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chat_id, chave)
);

CREATE TABLE tool_call_audit (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id       text,
    chat_id        text,
    tool_name      text NOT NULL,
    input_redacted jsonb,
    result_status  text NOT NULL CHECK (result_status IN ('ok','error','denied')),
    latency_ms     integer,
    error_code     text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Indices de consulta das ferramentas.
CREATE INDEX idx_titulares_telefone   ON titulares (telefone_principal);
CREATE INDEX idx_uc_bairro            ON unidades_consumidoras (bairro, cidade, uf);
CREATE INDEX idx_faturas_uc           ON faturas (uc_id);
CREATE INDEX idx_interrupcoes_area    ON interrupcoes (bairro, cidade, uf, status);
CREATE INDEX idx_chamados_titular     ON chamados (titular_id);
