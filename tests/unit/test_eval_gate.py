"""Score 0-100 + gate >= 85 do eval runner (R-01).

O CI (`/.github/workflows/ci.yml`, job `eval-gate`) reprova o merge quando o
score do agente fica abaixo do limiar. Estas funções são o núcleo determinístico
desse gate — testáveis sem subir o stack nem chamar o LLM. Cobre o cálculo do
score (`round(100 * PASS / TOTAL)`), o limiar configurável por env
(`EVAL_GATE_MIN` precede `EVAL_GATE`, default 85) e a decisão `>=`.
"""

from __future__ import annotations

import pytest

from src.evals.run import compute_score, gate_passes, gate_threshold


class TestComputeScore:
    def test_tudo_passa_e_cem(self) -> None:
        assert compute_score(10, 10) == 100

    def test_tudo_falha_e_zero(self) -> None:
        assert compute_score(0, 10) == 0

    def test_metade_e_cinquenta(self) -> None:
        assert compute_score(5, 10) == 50

    def test_arredonda_para_o_inteiro_mais_proximo(self) -> None:
        # 17/20 = 85.0 (limiar exato); 16/20 = 80; 13/15 = 86.66 -> 87.
        assert compute_score(17, 20) == 85
        assert compute_score(16, 20) == 80
        assert compute_score(13, 15) == 87

    def test_suite_vazia_e_zero_nao_aprova(self) -> None:
        # Ausência de evidência de qualidade não pode virar aprovação por vacuidade.
        assert compute_score(0, 0) == 0


class TestGateThreshold:
    def test_default_85(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_GATE_MIN", raising=False)
        monkeypatch.delenv("EVAL_GATE", raising=False)
        assert gate_threshold() == 85

    def test_eval_gate_min_tem_prioridade(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # EVAL_GATE_MIN é o nome usado no ci.yml; precede EVAL_GATE.
        monkeypatch.setenv("EVAL_GATE_MIN", "90")
        monkeypatch.setenv("EVAL_GATE", "70")
        assert gate_threshold() == 90

    def test_eval_gate_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_GATE_MIN", raising=False)
        monkeypatch.setenv("EVAL_GATE", "75")
        assert gate_threshold() == 75

    def test_vazio_cai_no_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVAL_GATE_MIN", "")
        monkeypatch.delenv("EVAL_GATE", raising=False)
        assert gate_threshold() == 85

    def test_valor_invalido_cai_no_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EVAL_GATE_MIN", "abc")
        monkeypatch.delenv("EVAL_GATE", raising=False)
        assert gate_threshold() == 85


class TestGatePasses:
    def test_acima_do_limiar_passa(self) -> None:
        assert gate_passes(90, 85) is True

    def test_no_limiar_passa(self) -> None:
        # Decisão é `>=`: score == gate aprova (85 é o piso aceitável).
        assert gate_passes(85, 85) is True

    def test_abaixo_do_limiar_reprova(self) -> None:
        assert gate_passes(84, 85) is False
