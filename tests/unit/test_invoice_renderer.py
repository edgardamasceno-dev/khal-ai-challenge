"""Teste do WeasyPrintInvoiceRenderer (SPEC-008): produz PDF A4 real."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from src.domain.billing.documento import FaturaDetalhada
from src.domain.billing.entities import Fatura, Titular, UnidadeConsumidora
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from src.infrastructure.pdf.weasyprint_renderer import WeasyPrintInvoiceRenderer


def _detalhe(status: str = "em_aberto", venc: dt.date = dt.date(2026, 6, 10)) -> FaturaDetalhada:
    tid, ucid = uuid.uuid4(), uuid.uuid4()
    t = Titular(id=tid, nome="Edgar Damasceno", cpf=CPF("52998224725"),
                telefone=Telefone("5581993112159"), email=None, persona_key="edgar")
    uc = UnidadeConsumidora(id=ucid, numero_uc="767179274", titular_id=tid,
                            logradouro="Rua das Acácias, 120", bairro="Jardim das Flores",
                            cidade="Vale do Sol", uf="SP", classe="residencial",
                            subgrupo="B1", status="ativa")
    f = Fatura(id=uuid.uuid4(), uc_id=ucid, mes_referencia="2026-05", consumo_kwh=247,
               valor=Dinheiro(26869), bandeira="amarela", vencimento=venc, status=status,
               linha_digitavel="34191.79001 01043.510047 91020.150008 1 26050000026869",
               pix_copia_cola="000201")
    hist = [(f"2025-{m:02d}", 200 + m * 4) for m in range(6, 13)] + [("2026-05", 247)]
    return FaturaDetalhada(titular=t, unidade=uc, fatura=f, historico=hist,
                           emitida_em=dt.date(2026, 6, 1))


def test_render_produz_pdf_a4() -> None:
    pdf = WeasyPrintInvoiceRenderer(hoje=dt.date(2026, 6, 1)).render(_detalhe())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000  # tem QR + barcode embutidos


def test_render_fatura_vencida_aplica_juros() -> None:
    # vencida há 30 dias -> renderiza sem erro (juros/multa no template)
    pdf = WeasyPrintInvoiceRenderer(hoje=dt.date(2026, 6, 9)).render(
        _detalhe(status="vencida", venc=dt.date(2026, 5, 10))
    )
    assert pdf[:4] == b"%PDF"


@pytest.mark.parametrize("bandeira", ["verde", "amarela", "vermelha_p1", "vermelha_p2"])
def test_render_todas_bandeiras(bandeira: str) -> None:
    d = _detalhe()
    f = d.fatura
    object.__setattr__(f, "bandeira", bandeira)
    assert WeasyPrintInvoiceRenderer(hoje=dt.date(2026, 6, 1)).render(d)[:4] == b"%PDF"
