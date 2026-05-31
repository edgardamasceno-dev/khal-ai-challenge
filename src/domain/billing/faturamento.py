"""Composição tarifária e atualização pós-vencimento (determinístico, SPEC-008).

Regras de negócio do faturamento usadas no PDF da fatura. Puro: sem I/O.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# Bandeira tarifária -> (adicional R$/kWh, cor hex, rótulo).
BANDEIRAS: dict[str, tuple[float, str, str]] = {
    "verde": (0.0, "#2e9e4f", "Verde"),
    "amarela": (0.01885, "#e7b400", "Amarela"),
    "vermelha_p1": (0.04463, "#d64545", "Vermelha P1"),
    "vermelha_p2": (0.07877, "#9b1c2e", "Vermelha P2"),
}
_CIP = 12.90  # Contribuição de Iluminação Pública (valor fixo de demo)


@dataclass(frozen=True)
class ItemComposicao:
    descricao: str
    quantidade: str
    tarifa: str
    valor: float


def composicao_tarifaria(total: float, consumo_kwh: int, bandeira: str) -> list[ItemComposicao]:
    """Decompõe o total em TE + TUSD + bandeira + CIP (soma == total).

    Tributos (ICMS/PIS/COFINS) são 'por dentro' no Brasil -> linha informativa.
    """
    if bandeira not in BANDEIRAS:
        raise ValueError(f"bandeira invalida: {bandeira!r}")
    rate = BANDEIRAS[bandeira][0]
    v_band = round(consumo_kwh * rate, 2)
    v_energia = round(total - v_band - _CIP, 2)
    te = round(v_energia * 0.42, 2)
    tusd = round(v_energia - te, 2)
    label = BANDEIRAS[bandeira][2]

    def por_kwh(v: float) -> str:
        return f"R$ {v / consumo_kwh:.4f}".replace(".", ",") if consumo_kwh else "—"

    return [
        ItemComposicao("Energia Elétrica – TE (consumo)", f"{consumo_kwh} kWh", por_kwh(te), te),
        ItemComposicao("Energia Elétrica – TUSD (distribuição)", f"{consumo_kwh} kWh", por_kwh(tusd), tusd),
        ItemComposicao(f"Adicional Bandeira {label}", f"{consumo_kwh} kWh",
                       f"R$ {rate:.4f}".replace(".", ","), v_band),
        ItemComposicao("Contrib. Iluminação Pública (CIP)", "—", "—", _CIP),
        ItemComposicao("Tributos inclusos: ICMS 18% · PIS 1,65% · COFINS 7,60%", "—", "—", 0.0),
    ]


@dataclass(frozen=True)
class AtualizacaoPosVencimento:
    dias_atraso: int
    multa: float  # 2% sobre o principal
    juros: float  # 1% a.m. (0,0333%/dia) pro rata
    total_atualizado: float


def atualizar_pos_vencimento(
    principal: float, vencimento: dt.date, hoje: dt.date
) -> AtualizacaoPosVencimento:
    """Multa de 2% + juros de mora de 1% a.m. (pro rata die) após o vencimento."""
    dias = (hoje - vencimento).days
    if dias <= 0:
        return AtualizacaoPosVencimento(0, 0.0, 0.0, round(principal, 2))
    multa = round(principal * 0.02, 2)
    juros = round(principal * 0.01 / 30 * dias, 2)
    return AtualizacaoPosVencimento(dias, multa, juros, round(principal + multa + juros, 2))
