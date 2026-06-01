"""Unit da tool ``get_consumption_insights`` (R-17 / SPEC-025): insights
DETERMINISTICOS de consumo (kWh) sobre ~24 meses do titular, read-only, com o
mesmo guardrail por telefone das demais tools.

Contrato verificado:
- shape estavel por UC (espelha list_contracts): media, tendencia, variacao do
  ultimo mes vs media, pico, comparativo sazonal YoY, ultimo mes;
- calculo deterministico, sem LLM e sem mutacao;
- guardrail: telefone sem titular -> encontrado=False, sem consultar consumo;
- multi-UC e UC sem historico tratados sem stacktrace (alinhado com M-03).

Os helpers de calculo (`_classificar_tendencia`, `_variacao_pct`,
`_comparativo_sazonal`) sao puros e testados isoladamente — a logica de insight
nao depende de rede.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.interfaces.mcp.tools import (
    CxTools,
    _classificar_tendencia,
    _comparativo_sazonal,
    _variacao_pct,
)
from tests.unit.mcp_fakes import FakeLegacyApiClient

ANA = "555199990001"
CARLOS = "555199990002"
DESCONHECIDO = "550000000000"


def _tools() -> CxTools:
    return CxTools(FakeLegacyApiClient())


# ------------------------------ helpers puros ------------------------------ #


class TestVariacaoPct:
    def test_aumento(self) -> None:
        assert _variacao_pct(150, 100.0) == 50.0

    def test_queda(self) -> None:
        assert _variacao_pct(80, 100.0) == -20.0

    def test_base_zero_nao_divide(self) -> None:
        # Sem media (base 0) -> 0.0, nunca ZeroDivisionError.
        assert _variacao_pct(100, 0.0) == 0.0


class TestClassificarTendencia:
    def test_subindo_acima_da_banda(self) -> None:
        # Ultimos 3 (290,295,300) muito acima da media global -> subindo.
        consumos = [100, 110, 120, 290, 295, 300]
        media = sum(consumos) / len(consumos)
        assert _classificar_tendencia(consumos, media) == "subindo"

    def test_caindo_abaixo_da_banda(self) -> None:
        consumos = [300, 295, 290, 110, 105, 100]
        media = sum(consumos) / len(consumos)
        assert _classificar_tendencia(consumos, media) == "caindo"

    def test_estavel_dentro_da_banda(self) -> None:
        # Variacao < 5% em torno da media -> estavel (banda morta evita ruido).
        consumos = [200, 201, 199, 200, 202, 198]
        media = sum(consumos) / len(consumos)
        assert _classificar_tendencia(consumos, media) == "estavel"

    def test_serie_curta_estavel(self) -> None:
        # Um unico mes nao tem evidencia de movimento.
        assert _classificar_tendencia([200], 200.0) == "estavel"


class TestComparativoSazonal:
    def test_casa_mesmo_mes_ano_anterior(self) -> None:
        historico = [
            {"mes": "2025-05", "kwh": 200},
            {"mes": "2025-06", "kwh": 210},
            {"mes": "2026-05", "kwh": 250},
        ]
        out = _comparativo_sazonal(historico)
        assert out["mesmo_mes_ano_anterior_kwh"] == 200
        assert out["variacao_pct_yoy"] == 25.0

    def test_sem_ano_anterior_retorna_none(self) -> None:
        # Historico < 1 ano: nao ha o mesmo mes no ano anterior -> None/None.
        historico = [{"mes": "2026-04", "kwh": 200}, {"mes": "2026-05", "kwh": 250}]
        out = _comparativo_sazonal(historico)
        assert out["mesmo_mes_ano_anterior_kwh"] is None
        assert out["variacao_pct_yoy"] is None


# --------------------------------- a tool ---------------------------------- #


class TestConsumptionInsights:
    def test_titular_com_historico_24_meses(self) -> None:
        r = _tools().get_consumption_insights(ANA)
        assert r["encontrado"] is True and r["titular"] == "Ana Souza"
        uc = r["unidades"][0]
        assert uc["numero_uc"] == "100000001"
        assert uc["meses_analisados"] == 24
        assert uc["media_kwh"] > 0

    def test_tendencia_subindo(self) -> None:
        # O historico da Ana cresce ao longo de ~24 meses -> tendencia 'subindo'.
        uc = _tools().get_consumption_insights(ANA)["unidades"][0]
        assert uc["tendencia"] == "subindo"

    def test_pico_isolado_de_verao(self) -> None:
        # Pico determinIstico em 2025-07 (590 kWh) — maior consumo da serie.
        uc = _tools().get_consumption_insights(ANA)["unidades"][0]
        assert uc["pico"]["mes_referencia"] == "2025-07"
        assert uc["pico"]["consumo_kwh"] == 590

    def test_comparativo_sazonal_yoy_do_ultimo_mes(self) -> None:
        # Ultimo mes 2026-05 casa com 2025-05 no historico (YoY presente).
        uc = _tools().get_consumption_insights(ANA)["unidades"][0]
        sazonal = uc["comparativo_sazonal"]
        assert sazonal["mesmo_mes_ano_anterior_kwh"] is not None
        assert sazonal["variacao_pct_yoy"] is not None
        assert uc["ultimo_mes"]["mes_referencia"] == "2026-05"

    def test_variacao_ultimo_vs_media_presente(self) -> None:
        uc = _tools().get_consumption_insights(ANA)["unidades"][0]
        assert isinstance(uc["variacao_pct_ult_vs_media"], float)

    def test_uc_com_historico_curto_sem_yoy(self) -> None:
        # Carlos tem 1 mes: tendencia estavel e sem comparativo ano-a-ano.
        r = _tools().get_consumption_insights(CARLOS)
        assert r["encontrado"] is True and r["titular"] == "Carlos Lima"
        uc = r["unidades"][0]
        assert uc["meses_analisados"] == 1
        assert uc["tendencia"] == "estavel"
        assert uc["comparativo_sazonal"]["mesmo_mes_ano_anterior_kwh"] is None

    def test_telefone_desconhecido_nao_consulta_consumo(self) -> None:
        # Guardrail: telefone sem titular -> encontrado=False e sem 'unidades'.
        r = _tools().get_consumption_insights(DESCONHECIDO)
        assert r["encontrado"] is False
        assert "unidades" not in r

    def test_um_bloco_por_uc_espelha_contratos(self) -> None:
        # Numero de blocos == numero de UCs do titular (espelha list_contracts).
        tools = _tools()
        contratos = tools.list_contracts(ANA)["unidades"]
        insights = tools.get_consumption_insights(ANA)["unidades"]
        assert len(insights) == len(contratos)

    def test_uc_sem_historico_nao_quebra(self) -> None:
        # UC sem nenhuma fatura -> bloco com meses_analisados=0 e observacao amigavel,
        # nunca stacktrace (alinhado com M-03).
        class _SemHistorico(FakeLegacyApiClient):
            def list_invoices(self, uc_id: str) -> list[dict[str, Any]]:
                return []

        r = CxTools(_SemHistorico()).get_consumption_insights(ANA)
        uc = r["unidades"][0]
        assert uc["meses_analisados"] == 0
        assert uc["pico"] is None and uc["ultimo_mes"] is None
        assert uc["observacao"]

    def test_read_only_nao_muta_estado(self) -> None:
        # Duas chamadas seguidas devolvem o mesmo resultado (idempotente, sem efeito).
        tools = _tools()
        a = tools.get_consumption_insights(ANA)
        b = tools.get_consumption_insights(ANA)
        assert a == b


def test_helpers_sao_puros_sem_rede() -> None:
    # Sanidade: os helpers de calculo nao tocam o client (sao funcoes puras).
    assert _variacao_pct(0, 0.0) == 0.0
    assert _classificar_tendencia([], 0.0) == "estavel"
    with pytest.raises(IndexError):
        _comparativo_sazonal([])  # exige historico nao-vazio (chamado internamente so com dados)
