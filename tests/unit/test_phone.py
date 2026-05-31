"""Testes da normalização de telefone e variantes do nono dígito (SPEC-015)."""

from __future__ import annotations

from src.domain.shared.phone import normalizar_msisdn, variantes_nono_digito


class TestNormalizar:
    def test_tira_sufixo_lid(self) -> None:
        assert normalizar_msisdn("87866608713902@lid") == "87866608713902"

    def test_tira_sufixo_whatsapp_e_simbolos(self) -> None:
        assert normalizar_msisdn("+55 81 99311-2159@s.whatsapp.net") == "5581993112159"

    def test_so_digitos(self) -> None:
        assert normalizar_msisdn("5581993112159") == "5581993112159"

    def test_vazio_invalido(self) -> None:
        assert normalizar_msisdn("@lid") == ""


class TestVariantesNonoDigito:
    def test_sem_9_gera_com_9(self) -> None:
        # canonical do Omni (sem 9) -> inclui a forma cadastrada (com 9)
        assert set(variantes_nono_digito("558193112159")) == {
            "558193112159",
            "5581993112159",
        }

    def test_com_9_gera_sem_9(self) -> None:
        assert set(variantes_nono_digito("5581993112159")) == {
            "5581993112159",
            "558193112159",
        }

    def test_idempotente_e_inclui_o_proprio(self) -> None:
        for numero in ("558193112159", "5581993112159"):
            assert numero in variantes_nono_digito(numero)

    def test_nao_celular_so_o_proprio(self) -> None:
        # LID puro (14 díg) ou número fora do padrão BR -> sem variação espúria
        assert variantes_nono_digito("87866608713902") == ["87866608713902"]
