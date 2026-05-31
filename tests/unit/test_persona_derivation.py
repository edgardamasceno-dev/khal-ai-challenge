"""Testes do domínio de personas (SPEC-006): derivação determinística."""

from __future__ import annotations

from src.domain.persona import perfil_de
from src.domain.persona.models import CENARIOS_FATURA
from src.domain.shared.value_objects import cpf_valido

EDGAR = "5581993112159"
SEED = 42


def test_determinismo_mesma_entrada_mesmo_perfil() -> None:
    a = perfil_de(EDGAR, SEED)
    b = perfil_de(EDGAR, SEED)
    assert a == b


def test_telefones_diferentes_geram_perfis_diferentes() -> None:
    p1 = perfil_de("5581993112159", SEED)
    p2 = perfil_de("555199990001", SEED)
    assert p1.cpf != p2.cpf


def test_seed_diferente_muda_o_perfil() -> None:
    assert perfil_de(EDGAR, 42) != perfil_de(EDGAR, 7)


def test_cpf_gerado_tem_dv_valido() -> None:
    for phone in ("5581993112159", "555199990001", "5511987654321", "5599911112222"):
        assert cpf_valido(perfil_de(phone, SEED).cpf)


def test_invariantes_do_perfil() -> None:
    p = perfil_de(EDGAR, SEED)
    assert p.cenario_fatura in CENARIOS_FATURA
    assert 1 <= p.n_ucs <= 4
    assert len(p.base_kwh) == p.n_ucs
    assert all(k > 0 for k in p.base_kwh)
    assert p.classe in ("residencial", "comercial", "rural")


def test_n_ucs_de_1_a_4_cobre_a_faixa() -> None:
    # Numa amostra determinística, a distribuição deve usar os 4 valores (1..4).
    vistos = {perfil_de(f"55119{i:07d}", SEED).n_ucs for i in range(200)}
    assert vistos == {1, 2, 3, 4}


def test_cenarios_canonicos_preservados() -> None:
    # A derivação de n_ucs (stream dedicado) NÃO desloca cenário/outage/corte
    # das personas residenciais/rurais existentes (regressão SPEC-013).
    esperado = {
        "555199990001": ("uma_vencida", False, False),  # Ana
        "555199990002": ("uma_aberta", False, False),  # Carlos
        "555199990003": ("uma_vencida", False, False),  # Joana
        EDGAR: ("em_dia", False, False),
    }
    for phone, (cenario, outage, corte) in esperado.items():
        p = perfil_de(phone, SEED)
        assert (p.cenario_fatura, p.outage_ativa, p.corte_religacao) == (cenario, outage, corte)


def test_perfil_rico_garante_cenario_demonstravel() -> None:
    p = perfil_de(EDGAR, SEED, rico=True)
    assert p.cenario_fatura == "uma_vencida"
    assert p.outage_ativa is True
    assert p.bairro == "Jardim das Flores"


def test_multiplos_telefones_cpfs_unicos() -> None:
    phones = [f"55819931121{n:02d}" for n in range(50)]
    cpfs = {perfil_de(p, SEED).cpf for p in phones}
    assert len(cpfs) == len(phones)  # sem colisão de CPF
