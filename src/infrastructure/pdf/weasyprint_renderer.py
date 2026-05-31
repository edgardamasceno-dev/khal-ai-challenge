"""Adapter de render da fatura em PDF A4 (WeasyPrint). Implementa InvoicePdfRenderer.

Imports pesados (weasyprint/qrcode/barcode) são lazy: o módulo importa barato; só
`render()` exige as libs. Usa as regras do domínio (composição, juros, PIX, boleto).
"""

from __future__ import annotations

import base64
import datetime as dt
import importlib.resources as resources
import io
from typing import Any

from src.domain.billing.documento import FaturaDetalhada
from src.domain.billing.faturamento import (
    BANDEIRAS,
    atualizar_pos_vencimento,
    composicao_tarifaria,
)
from src.domain.billing.pagamento_codes import boleto_barcode_digits, pix_emv

_MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
_STATUS = {
    "em_aberto": ("EM ABERTO", "b-aberto", "EM ABERTO", "Pague até o vencimento para evitar multa e juros."),
    "vencida": ("VENCIDA", "b-vencida", "VENCIDA", "Fatura vencida — sujeita a multa e juros."),
    "paga": ("PAGA", "b-paga", "PAGA", "Fatura quitada. Obrigado!"),
}


def _brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mask_cpf(cpf: str) -> str:
    d = "".join(c for c in cpf if c.isdigit()).ljust(11, "0")
    return f"{d[:3]}.***.**{d[9:]}"


class WeasyPrintInvoiceRenderer:
    """Renderer A4 via HTML/CSS + WeasyPrint, com QR PIX e código de barras."""

    def __init__(self, hoje: dt.date | None = None) -> None:
        self._hoje = hoje  # injetável p/ determinismo em teste

    def _qr_b64(self, data: str) -> str:
        import qrcode  # lazy

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        buf = io.BytesIO()
        qr.make_image(fill_color="#0a2230", back_color="white").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def _barcode_b64(self, linha: str | None) -> str:
        import barcode  # lazy
        from barcode.writer import ImageWriter

        digits = boleto_barcode_digits(linha)
        buf = io.BytesIO()
        barcode.get("itf", digits, writer=ImageWriter()).write(
            buf, options={"module_height": 12.0, "module_width": 0.32, "quiet_zone": 2,
                          "write_text": False, "background": "white", "foreground": "#0a2230"},
        )
        return base64.b64encode(buf.getvalue()).decode()

    def _context(self, d: FaturaDetalhada) -> dict[str, Any]:
        f, uc, t = d.fatura, d.unidade, d.titular
        ano, mes = (int(x) for x in f.mes_referencia.split("-"))
        principal = f.valor.reais
        hoje = self._hoje or dt.date.today()
        atual = atualizar_pos_vencimento(principal, f.vencimento, hoje)
        vencida = f.status == "vencida" and atual.dias_atraso > 0
        total = atual.total_atualizado if vencida else principal
        slabel, sclass, swm, shelp = _STATUS.get(f.status, _STATUS["em_aberto"])
        cor, blabel = BANDEIRAS.get(f.bandeira, BANDEIRAS["verde"])[1:3]

        hist = d.historico[-12:]
        mx = max((k for _, k in hist), default=1) or 1
        historico = [{"kwh": k, "mes": _MESES[int(m.split("-")[1])][:3], "pct": int(28 + 72 * k / mx)}
                     for m, k in hist]
        emissao = (d.emitida_em or hoje).strftime("%d/%m/%Y")
        pix = pix_emv("financeiro@luzdovale.com.br", "LUZ DO VALE DISTRIB",
                      (uc.cidade or "VALE DO SOL").upper(), total, f"LDV{f.mes_referencia.replace('-','')}{uc.numero_uc}")
        juros_info = (
            f"Valor original R$ {_brl(principal)} + multa R$ {_brl(atual.multa)} + "
            f"juros R$ {_brl(atual.juros)} ({atual.dias_atraso} dias)."
            if vencida else "Valor atualizado calculado na data do pagamento."
        )
        return {
            "status_wm": swm, "mes_extenso": f"{_MESES[mes].upper()}/{ano}",
            "numero_fatura": f"{uc.numero_uc}-{mes:02d}", "status_label": slabel, "status_class": sclass,
            "nome": t.nome, "cpf_mask": _mask_cpf(t.cpf.value),
            "endereco": uc.logradouro or "—", "bairro": uc.bairro, "cidade": uc.cidade, "uf": uc.uf,
            "numero_uc": uc.numero_uc, "classe": (uc.classe or "").capitalize(), "subgrupo": uc.subgrupo or "—",
            "mes_ref": f"{mes:02d}/{ano}", "emissao": emissao, "vencimento": f.vencimento.strftime("%d/%m/%Y"),
            "consumo": f.consumo_kwh, "bandeira_cor": cor, "bandeira_label": blabel,
            "media_dia": round(f.consumo_kwh / 30, 1), "status_help": shelp, "total": _brl(total),
            "itens": [{"desc": i.descricao, "qtd": i.quantidade, "tarifa": i.tarifa, "valor": _brl(i.valor)}
                      for i in composicao_tarifaria(principal, f.consumo_kwh, f.bandeira)],
            "historico": historico,
            "media_12m": round(sum(k for _, k in hist) / len(hist)) if hist else f.consumo_kwh,
            "consumo_ano_ant": next((k for m, k in hist if m.endswith(f"-{mes:02d}") and m != f.mes_referencia), f.consumo_kwh),
            "qr_b64": self._qr_b64(pix), "pix_cc": pix,
            "barcode_b64": self._barcode_b64(f.linha_digitavel),
            "linha_digitavel": f.linha_digitavel or "—", "juros_info": juros_info,
        }

    def render(self, detalhe: FaturaDetalhada) -> bytes:
        from jinja2 import Template
        from weasyprint import HTML  # lazy (libs de sistema)

        tpl = resources.files("src.infrastructure.pdf.templates").joinpath("fatura.html").read_text("utf-8")
        html = Template(tpl).render(**self._context(detalhe))
        pdf: bytes = HTML(string=html).write_pdf()
        return pdf
