"""Testes do faturamento/códigos de pagamento (SPEC-008)."""

from __future__ import annotations

import datetime as dt

import pytest

from src.domain.billing.faturamento import (
    atualizar_pos_vencimento,
    composicao_tarifaria,
)
from src.domain.billing.pagamento_codes import (
    _crc16,
    boleto_barcode_digits,
    pix_emv,
)


def test_composicao_soma_o_total() -> None:
    itens = composicao_tarifaria(268.69, 247, "amarela")
    assert round(sum(i.valor for i in itens), 2) == 268.69
    assert any("Bandeira Amarela" in i.descricao for i in itens)


def test_composicao_bandeira_invalida() -> None:
    with pytest.raises(ValueError, match="bandeira"):
        composicao_tarifaria(100.0, 100, "roxa")


def test_pos_vencimento_em_dia_nao_aplica() -> None:
    a = atualizar_pos_vencimento(100.0, dt.date(2026, 6, 10), dt.date(2026, 6, 5))
    assert a.dias_atraso == 0
    assert a.total_atualizado == 100.0


def test_pos_vencimento_multa_e_juros() -> None:
    a = atualizar_pos_vencimento(100.0, dt.date(2026, 5, 10), dt.date(2026, 6, 9))
    assert a.dias_atraso == 30
    assert a.multa == 2.0  # 2%
    assert a.juros == 1.0  # 1% a.m. por 30 dias
    assert a.total_atualizado == 103.0


def test_pix_emv_estruturado_com_crc_valido() -> None:
    emv = pix_emv("financeiro@luzdovale.com.br", "LUZ DO VALE", "VALE DO SOL", 268.69, "LDV202605")
    assert emv.startswith("000201")
    assert "BR.GOV.BCB.PIX" in emv
    assert "5406268.69" in emv  # tag 54 (valor)
    # CRC16: recomputar sobre tudo menos os 4 últimos dígitos deve bater.
    assert _crc16(emv[:-4]) == emv[-4:]


def test_boleto_barcode_44_digitos() -> None:
    d = boleto_barcode_digits("34191.79001 01043.510047 91020.150008 1 26050000026869")
    assert len(d) == 44
    assert d.isdigit()
    assert boleto_barcode_digits(None) == "0" * 44
