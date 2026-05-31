from __future__ import annotations

import pytest

from src.domain.shared.errors import InvariantError
from src.domain.shared.value_objects import (
    CPF,
    Dinheiro,
    MesReferencia,
    Protocolo,
    StatusChamado,
    Telefone,
    TipoChamado,
)


class TestCPF:
    def test_aceita_valido_e_normaliza(self) -> None:
        cpf = CPF("529.982.247-25")  # ficticio, DV valido
        assert cpf.value == "52998224725"

    def test_mascara_preserva_pontas(self) -> None:
        assert CPF("52998224725").mascarado() == "529.***.***-25"

    @pytest.mark.parametrize("invalido", ["123.456.789-00", "11111111111", "123", ""])
    def test_rejeita_invalido(self, invalido: str) -> None:
        with pytest.raises(InvariantError):
            CPF(invalido)


class TestTelefone:
    def test_normaliza_digitos(self) -> None:
        assert Telefone("+55 (11) 99999-0001").value == "5511999990001"

    def test_mascara(self) -> None:
        assert Telefone("555199990001").mascarado() == "5551****01"

    @pytest.mark.parametrize("invalido", ["123", "", "1234567890123456"])
    def test_rejeita_invalido(self, invalido: str) -> None:
        with pytest.raises(InvariantError):
            Telefone(invalido)


class TestDinheiro:
    def test_formata_reais(self) -> None:
        d = Dinheiro(12345)
        assert d.formatado() == "R$ 123.45"
        assert d.reais == 123.45

    @pytest.mark.parametrize("invalido", [-1, True, 1.5])
    def test_rejeita_invalido(self, invalido: object) -> None:
        with pytest.raises(InvariantError):
            Dinheiro(invalido)  # type: ignore[arg-type]


class TestMesReferencia:
    def test_aceita_valido(self) -> None:
        assert MesReferencia("2026-05").value == "2026-05"

    @pytest.mark.parametrize("invalido", ["2026-13", "2026-00", "26-05", "2026/05", ""])
    def test_rejeita_invalido(self, invalido: str) -> None:
        with pytest.raises(InvariantError):
            MesReferencia(invalido)


class TestProtocolo:
    def test_gera_formato_valido(self) -> None:
        p = Protocolo.gerar("20260530", "ab12")
        assert p.value == "LDV20260530AB12"

    @pytest.mark.parametrize("invalido", ["LDV2026", "ABC20260530AAAA", ""])
    def test_rejeita_invalido(self, invalido: str) -> None:
        with pytest.raises(InvariantError):
            Protocolo(invalido)


class TestTipoChamado:
    def test_sla_por_tipo(self) -> None:
        assert TipoChamado.falta_energia.sla_horas == 48
        assert TipoChamado.religacao.sla_horas == 24
        assert TipoChamado.titularidade.sla_horas == 72

    def test_valor_invalido(self) -> None:
        with pytest.raises(ValueError):
            TipoChamado("xpto")


class TestStatusChamado:
    def test_expoe_exatamente_aberto_e_resolvido(self) -> None:
        # SPEC-020: por ora o ciclo de vida tem so estes dois estados.
        assert {s.value for s in StatusChamado} == {"aberto", "resolvido"}
        assert StatusChamado.aberto.value == "aberto"
        assert StatusChamado.resolvido.value == "resolvido"

    @pytest.mark.parametrize("invalido", ["cancelado", "em_andamento", "ABERTO", ""])
    def test_valor_invalido(self, invalido: str) -> None:
        with pytest.raises(ValueError):
            StatusChamado(invalido)
