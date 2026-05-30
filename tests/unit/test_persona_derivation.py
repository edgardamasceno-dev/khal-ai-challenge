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
    assert p.n_ucs in (1, 2)
    assert len(p.base_kwh) == p.n_ucs
    assert all(k > 0 for k in p.base_kwh)
    assert p.classe in ("residencial", "comercial", "rural")


def test_perfil_rico_garante_cenario_demonstravel() -> None:
    p = perfil_de(EDGAR, SEED, rico=True)
    assert p.cenario_fatura == "uma_vencida"
    assert p.outage_ativa is True
    assert p.bairro == "Jardim das Flores"


def test_multiplos_telefones_cpfs_unicos() -> None:
    phones = [f"55819931121{n:02d}" for n in range(50)]
    cpfs = {perfil_de(p, SEED).cpf for p in phones}
    assert len(cpfs) == len(phones)  # sem colisão de CPF
