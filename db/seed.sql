-- Seed determinístico da "Luz do Vale" (docs/domain/seed-design.md + personas-journeys.md).
-- Idempotente por chave natural (CPF, numero_uc, mes_referencia, protocolo, idempotency_key).
-- Mes de referencia ancora: 2026-05. Historico de 24 meses (2024-06 .. 2026-05).
-- CPFs ficticios com digito verificador valido. Telefones via :phone_* (do .env).

BEGIN;

-- ---------------------------------------------------------------------------
-- Titulares (3 personas). CPFs validos no modulo 11, porem ficticios.
-- ---------------------------------------------------------------------------
INSERT INTO titulares (id, nome, cpf, email, telefone_principal, persona_key) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Ana Souza',     '52998224725', 'ana.souza@example.test',     :'phone_primary', 'ana.souza'),
  ('22222222-2222-2222-2222-222222222222', 'Carlos Lima',   '11144477735', 'carlos.lima@example.test',   :'phone_eval1',   'carlos.lima'),
  ('33333333-3333-3333-3333-333333333333', 'Joana Pereira', '22233344405', 'joana.pereira@example.test', :'phone_eval2',   'joana.pereira')
ON CONFLICT (cpf) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Unidades consumidoras. Ana 1 (Jardim das Flores), Carlos 2, Joana 1 (rural).
-- ---------------------------------------------------------------------------
INSERT INTO unidades_consumidoras
  (id, numero_uc, titular_id, logradouro, bairro, cidade, uf, cep, classe, subgrupo, status, data_ligacao) VALUES
  ('aaaa0001-0000-0000-0000-000000000001', '100000001', '11111111-1111-1111-1111-111111111111',
     'Rua das Acacias, 120', 'Jardim das Flores', 'Vale do Sol', 'SP', '13900000', 'residencial', 'B1', 'ativa', DATE '2019-03-10'),
  ('cccc0001-0000-0000-0000-000000000001', '200000001', '22222222-2222-2222-2222-222222222222',
     'Av. Central, 800 - Loja', 'Centro', 'Vale do Sol', 'SP', '13900100', 'comercial', 'B3', 'ativa', DATE '2017-08-01'),
  ('cccc0002-0000-0000-0000-000000000002', '200000002', '22222222-2222-2222-2222-222222222222',
     'Rua do Comercio, 45 - Deposito', 'Distrito Industrial', 'Vale do Sol', 'SP', '13900200', 'comercial', 'B3', 'ativa', DATE '2018-02-15'),
  ('dddd0001-0000-0000-0000-000000000001', '300000001', '33333333-3333-3333-3333-333333333333',
     'Estrada Rural do Vale, km 12', 'Zona Rural', 'Vale do Sol', 'SP', '13900900', 'rural', 'B2', 'ativa', DATE '2020-11-20')
ON CONFLICT (numero_uc) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Contratos (um por UC).
-- ---------------------------------------------------------------------------
INSERT INTO contratos (titular_id, uc_id, modalidade, data_inicio, status)
SELECT uc.titular_id, uc.id, 'convencional', uc.data_ligacao, 'ativo'
FROM unidades_consumidoras uc
WHERE NOT EXISTS (SELECT 1 FROM contratos c WHERE c.uc_id = uc.id);

-- ---------------------------------------------------------------------------
-- Leituras: 24 meses por UC, com sazonalidade (verao dez-mar +35%).
-- ---------------------------------------------------------------------------
WITH uc_base AS (
    SELECT * FROM (VALUES
        ('aaaa0001-0000-0000-0000-000000000001'::uuid, 180),
        ('cccc0001-0000-0000-0000-000000000001'::uuid, 620),
        ('cccc0002-0000-0000-0000-000000000002'::uuid, 410),
        ('dddd0001-0000-0000-0000-000000000001'::uuid, 240)
    ) AS t(uc_id, base_kwh)
),
meses AS (
    SELECT
        to_char((DATE '2026-05-01' - (g || ' months')::interval), 'YYYY-MM') AS mes_ref,
        EXTRACT(MONTH FROM (DATE '2026-05-01' - (g || ' months')::interval))::int AS mnum
    FROM generate_series(0, 23) AS g
)
INSERT INTO leituras (uc_id, mes_referencia, consumo_kwh, data_leitura)
SELECT
    b.uc_id,
    m.mes_ref,
    b.base_kwh
      + CASE WHEN m.mnum IN (12, 1, 2, 3) THEN (b.base_kwh * 35 / 100) ELSE 0 END
      + m.mnum,                                   -- variacao deterministica leve
    (m.mes_ref || '-05')::date
FROM uc_base b CROSS JOIN meses m
ON CONFLICT (uc_id, mes_referencia) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Faturas: uma por leitura. Tarifa ~ R$0,95/kWh + adicional de bandeira.
-- Bandeira correlacionada a meses secos/quentes. Default status 'paga'.
-- ---------------------------------------------------------------------------
INSERT INTO faturas
  (uc_id, mes_referencia, consumo_kwh, valor_total_centavos, bandeira, vencimento, status, linha_digitavel, pix_copia_cola, emitida_em)
SELECT
    l.uc_id,
    l.mes_referencia,
    l.consumo_kwh,
    l.consumo_kwh * 95
      + l.consumo_kwh * CASE band.bandeira
            WHEN 'amarela'     THEN 2
            WHEN 'vermelha_p1' THEN 4
            WHEN 'vermelha_p2' THEN 7
            ELSE 0 END,
    band.bandeira,
    (l.mes_referencia || '-01')::date + INTERVAL '1 month 9 days',  -- ~dia 10 do mes seguinte
    'paga',
    '34191.79001 01043.510047 91020.150008 1 ' || replace(l.mes_referencia, '-', '') || '00',
    '00020126LUZDOVALEFICTICIO' || replace(l.mes_referencia, '-', ''),
    (l.mes_referencia || '-01')::timestamptz + INTERVAL '1 day'
FROM leituras l
CROSS JOIN LATERAL (
    SELECT CASE substring(l.mes_referencia FROM 6 FOR 2)::int
        WHEN 8 THEN 'vermelha_p2' WHEN 9 THEN 'vermelha_p2'
        WHEN 6 THEN 'vermelha_p1' WHEN 7 THEN 'vermelha_p1'
        WHEN 10 THEN 'vermelha_p1' WHEN 11 THEN 'vermelha_p1'
        WHEN 4 THEN 'amarela' WHEN 5 THEN 'amarela' WHEN 12 THEN 'amarela'
        ELSE 'verde' END AS bandeira
) band
ON CONFLICT (uc_id, mes_referencia) DO NOTHING;

-- Estado de demo da Ana: mes atual em aberto, mes anterior vencido.
UPDATE faturas SET status = 'em_aberto'
  WHERE uc_id = 'aaaa0001-0000-0000-0000-000000000001' AND mes_referencia = '2026-05';
UPDATE faturas SET status = 'vencida'
  WHERE uc_id = 'aaaa0001-0000-0000-0000-000000000001' AND mes_referencia = '2026-04';

-- ---------------------------------------------------------------------------
-- Pagamentos: um por fatura paga, com idempotency_key estavel.
-- ---------------------------------------------------------------------------
INSERT INTO pagamentos (fatura_id, valor_centavos, data_pagamento, meio, idempotency_key)
SELECT
    f.id,
    f.valor_total_centavos,
    (f.mes_referencia || '-15')::timestamptz + INTERVAL '1 month',
    'pix',
    'pay-' || f.uc_id || '-' || f.mes_referencia
FROM faturas f
WHERE f.status = 'paga'
ON CONFLICT (idempotency_key) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Interrupcoes: 1 ativa no bairro da Ana + historicas encerradas.
-- (datas relativas ao agora p/ a outage ativa ser demonstravel)
-- ---------------------------------------------------------------------------
INSERT INTO interrupcoes (bairro, cidade, uf, tipo, causa, inicio, previsao_retorno, status, encerrada_em)
SELECT v.bairro, v.cidade, v.uf, v.tipo, v.causa, v.inicio, v.previsao_retorno, v.status, v.encerrada_em
FROM (VALUES
    ('Jardim das Flores', 'Vale do Sol', 'SP', 'nao_programada', 'Falha em equipamento de rede',
        now() - INTERVAL '2 hours', now() + INTERVAL '3 hours', 'ativa', NULL::timestamptz),
    ('Jardim das Flores', 'Vale do Sol', 'SP', 'programada', 'Manutencao preventiva em alimentador',
        now() - INTERVAL '40 days', now() - INTERVAL '40 days' + INTERVAL '4 hours', 'encerrada', now() - INTERVAL '40 days' + INTERVAL '3 hours'),
    ('Centro', 'Vale do Sol', 'SP', 'nao_programada', 'Queda de arvore sobre a rede',
        now() - INTERVAL '15 days', now() - INTERVAL '15 days' + INTERVAL '5 hours', 'encerrada', now() - INTERVAL '15 days' + INTERVAL '4 hours')
) AS v(bairro, cidade, uf, tipo, causa, inicio, previsao_retorno, status, encerrada_em)
WHERE NOT EXISTS (
    -- Guard por chave natural estavel (bairro+causa): re-rodar nao duplica.
    -- Nao usar `inicio` aqui: ele depende de now() e mudaria a cada execucao.
    SELECT 1 FROM interrupcoes i
    WHERE i.bairro = v.bairro AND i.causa = v.causa
);

-- ---------------------------------------------------------------------------
-- Chamados: historicos resolvidos + 1 aberto (J4 follow-up) + religacao (Joana).
-- ---------------------------------------------------------------------------
INSERT INTO chamados
  (protocolo, titular_id, uc_id, tipo, descricao, status, sla_horas, canal, aberto_em, atualizado_em, idempotency_key) VALUES
  ('LDV2026040001', '33333333-3333-3333-3333-333333333333', 'dddd0001-0000-0000-0000-000000000001',
     'religacao', 'Religacao apos quitacao de debito que gerou corte', 'resolvido', 24, 'whatsapp',
     now() - INTERVAL '45 days', now() - INTERVAL '44 days', 'tk-joana-religacao'),
  ('LDV2026030007', '22222222-2222-2222-2222-222222222222', 'cccc0001-0000-0000-0000-000000000001',
     'segunda_via', 'Pedido de segunda via da fatura da loja', 'resolvido', 48, 'whatsapp',
     now() - INTERVAL '70 days', now() - INTERVAL '69 days', 'tk-carlos-2via'),
  ('LDV2026050010', '11111111-1111-1111-1111-111111111111', 'aaaa0001-0000-0000-0000-000000000001',
     'falta_energia', 'Cliente relatou falta de energia no Jardim das Flores', 'aberto', 48, 'whatsapp',
     now() - INTERVAL '1 day', now() - INTERVAL '1 day', 'tk-ana-falta-energia')
ON CONFLICT (idempotency_key) DO NOTHING;

COMMIT;

-- Resumo (mascarando telefone).
\echo '== Seed Luz do Vale =='
SELECT 'titulares' AS tabela, count(*) FROM titulares
UNION ALL SELECT 'unidades_consumidoras', count(*) FROM unidades_consumidoras
UNION ALL SELECT 'contratos', count(*) FROM contratos
UNION ALL SELECT 'leituras', count(*) FROM leituras
UNION ALL SELECT 'faturas', count(*) FROM faturas
UNION ALL SELECT 'pagamentos', count(*) FROM pagamentos
UNION ALL SELECT 'interrupcoes', count(*) FROM interrupcoes
UNION ALL SELECT 'chamados', count(*) FROM chamados
ORDER BY tabela;
