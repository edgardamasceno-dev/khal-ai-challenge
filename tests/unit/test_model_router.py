"""Roteador de modelo determinístico por caso (R-09 / ADR-0014 pilar 3).

Tabela ``mensagem -> tier`` mais a estabilidade da heurística (acento/caixa/
pontuação não mudam a decisão) e o mapeamento ``Modelo -> --model``. Puro, sem
I/O nem LLM.
"""

from __future__ import annotations

import pytest

from src.agent.model_router import Modelo, cli_model_flag, rotear_modelo


class TestTabelaRoteamento:
    """Casos canônicos: a coluna esperada espelha a política do ADR-0014."""

    @pytest.mark.parametrize(
        ("mensagem", "esperado"),
        [
            # OPUS — disputa / handoff / jurídico (alto valor).
            ("Quero falar com um atendente humano", Modelo.OPUS),
            ("Preciso falar com um humano agora", Modelo.OPUS),
            ("Isso é um absurdo, não concordo com essa cobrança", Modelo.OPUS),
            ("Vou abrir uma reclamação formal", Modelo.OPUS),
            ("Vou acionar o Procon e meu advogado", Modelo.OPUS),
            ("Quero cancelar meu contrato", Modelo.OPUS),
            # HAIKU — saudação / FAQ curta de KB (barato, alto volume).
            ("Oi, bom dia!", Modelo.HAIKU),
            ("Olá", Modelo.HAIKU),
            ("Qual o prazo de religação?", Modelo.HAIKU),
            ("O que é bandeira tarifária?", Modelo.HAIKU),
            ("Como faço para transferir a titularidade?", Modelo.HAIKU),
            # SONNET — transacional (default seguro).
            ("Preciso da segunda via da minha fatura", Modelo.SONNET),
            ("Qual o valor e o vencimento da minha conta?", Modelo.SONNET),
            ("Estou sem luz aqui no bairro, o que houve?", Modelo.SONNET),
            ("Quero o status do meu chamado", Modelo.SONNET),
            ("Me manda o PDF da fatura por favor", Modelo.SONNET),
        ],
    )
    def test_roteia(self, mensagem: str, esperado: Modelo) -> None:
        assert rotear_modelo(mensagem, primeiro_turno=True) == esperado


class TestPrioridadeEDefault:
    def test_opus_vence_haiku_em_msg_mista(self) -> None:
        # "bom dia" (haiku) + "falar com humano" (opus) → opus vence (alto valor).
        assert rotear_modelo("Bom dia, quero falar com um humano") == Modelo.OPUS

    def test_transacional_sobrepoe_haiku(self) -> None:
        # "oi" (saudação) + "segunda via fatura" (transacional) → sonnet, não haiku.
        assert rotear_modelo("Oi, preciso da segunda via da fatura") == Modelo.SONNET

    def test_default_seguro_para_vazio(self) -> None:
        assert rotear_modelo("") == Modelo.SONNET
        assert rotear_modelo("   ") == Modelo.SONNET

    def test_default_seguro_para_desconhecido(self) -> None:
        # Sem token de KB/disputa nem transacional → não subdimensiona: sonnet.
        assert rotear_modelo("xyzzy frobnicate quux") == Modelo.SONNET

    def test_msg_curta_sem_sinal_so_e_haiku_no_primeiro_turno(self) -> None:
        # "tudo bem?" curto: haiku só na abertura; fora do 1º turno, default sonnet.
        assert rotear_modelo("tudo bem?", primeiro_turno=True) == Modelo.HAIKU
        assert rotear_modelo("tudo bem?", primeiro_turno=False) == Modelo.SONNET


class TestEstabilidade:
    @pytest.mark.parametrize(
        "variante",
        ["Não concordo", "nao concordo", "NÃO CONCORDO", "não concordo!!!"],
    )
    def test_invariante_a_acento_e_caixa(self, variante: str) -> None:
        # strip-accents + lower + tokenize → mesma decisão para todas as variantes.
        assert rotear_modelo(variante) == Modelo.OPUS

    def test_idempotente(self) -> None:
        msg = "Quero a segunda via da fatura"
        assert rotear_modelo(msg) == rotear_modelo(msg)


class TestCliFlag:
    @pytest.mark.parametrize(
        ("modelo", "flag"),
        [(Modelo.HAIKU, "haiku"), (Modelo.SONNET, "sonnet"), (Modelo.OPUS, "opus")],
    )
    def test_mapeia_para_flag(self, modelo: Modelo, flag: str) -> None:
        assert cli_model_flag(modelo) == flag


class TestParidadeComCenarios:
    """M-08: todo cenário que declara ``expected_model`` deve bater com o roteador.

    Guarda o contrato eval↔roteador: se um cenário espera ``haiku`` mas a heurística
    devolve ``sonnet``, o eval acusaria FAIL de roteamento ao vivo — este teste
    pega o drift antes, sem gastar turno de LLM.
    """

    def test_cenarios_com_expected_model_batem(self) -> None:
        from src.evals.journeys import SCENARIOS

        verificados = 0
        for sc in SCENARIOS:
            if sc.expected_model is None:
                continue
            verificados += 1
            tier = rotear_modelo(sc.message, primeiro_turno=True)
            assert tier.value == sc.expected_model, (
                f"{sc.name}: roteador={tier.value} != esperado={sc.expected_model} "
                f"(msg={sc.message!r})"
            )
        assert verificados >= 3, "esperava ≥3 cenários cobrindo os 3 tiers (R-09/M-08)"
