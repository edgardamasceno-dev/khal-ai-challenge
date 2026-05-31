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


def test_derivacao_pura_baseline_preservada() -> None:
    # Sem `nome`/`persona_key`, a derivação por hash é a de sempre: o stream
    # dedicado de n_ucs (SPEC-013) NÃO desloca cenário/outage/corte. Trava o
    # baseline que o overlay canônico (ADR-0011) NÃO pode alterar.
    esperado = {
        "555199990001": ("uma_vencida", False, False),  # Ana (telefone)
        "555199990002": ("uma_aberta", False, False),  # Carlos (telefone)
        "555199990003": ("uma_vencida", False, False),  # Joana (telefone)
        EDGAR: ("em_dia", False, False),
    }
    for phone, (cenario, outage, corte) in esperado.items():
        p = perfil_de(phone, SEED)
        assert (p.cenario_fatura, p.outage_ativa, p.corte_religacao) == (cenario, outage, corte)


# --- Cenários canônicos por NOME (ADR-0011): fixos, não mais sorteados. ---

ANA_TEL = "555199990001"
CARLOS_TEL = "555199990002"
JOANA_TEL = "555199990003"


def test_canonico_ana_outage_e_fatura_vencida() -> None:
    p = perfil_de(ANA_TEL, SEED, nome="Ana Souza")
    assert p.classe == "residencial"
    assert p.bairro == "Jardim das Flores"
    assert p.cenario_fatura == "uma_vencida"
    assert p.outage_ativa is True


def test_canonico_carlos_comercial_multi_uc_em_dia() -> None:
    p = perfil_de(CARLOS_TEL, SEED, nome="Carlos Lima")
    assert p.classe == "comercial"
    assert p.n_ucs >= 2
    assert len(p.base_kwh) == p.n_ucs
    assert p.cenario_fatura == "em_dia"
    assert p.outage_ativa is False


def test_canonico_joana_rural_com_corte_religacao() -> None:
    p = perfil_de(JOANA_TEL, SEED, nome="Joana Pereira")
    assert p.classe == "rural"
    assert p.corte_religacao is True


def test_canonico_independe_do_telefone() -> None:
    # O overlay é por NOME (persona_key), não por telefone: Ana com qualquer
    # telefone mantém o cenário canônico (bairro/outage/fatura).
    p = perfil_de("5599911112222", SEED, nome="Ana Souza")
    assert p.bairro == "Jardim das Flores"
    assert p.outage_ativa is True
    assert p.cenario_fatura == "uma_vencida"


def test_persona_key_equivale_ao_nome() -> None:
    # Passar persona_key (slug pronto) é equivalente a passar o nome.
    por_nome = perfil_de(ANA_TEL, SEED, nome="Ana Souza")
    por_key = perfil_de(ANA_TEL, SEED, persona_key="ana.souza")
    assert por_nome == por_key


def test_nome_nao_canonico_nao_altera_o_perfil_derivado() -> None:
    # Telefone fora do conjunto canônico: passar um nome qualquer NÃO muda nada
    # em relação à derivação pura (a fixação é cirúrgica, só os 3 canônicos).
    for tel in ("555199990099", EDGAR, "5511987654321"):
        assert perfil_de(tel, SEED, nome="Fulano de Tal") == perfil_de(tel, SEED)


def test_canonico_tem_precedencia_sobre_rico() -> None:
    # Persona única canônica: canônico-por-nome > rico. Carlos não vira "rico"
    # (que forçaria residencial/uma_vencida/outage); mantém o cenário comercial.
    p = perfil_de("5599911112222", SEED, rico=True, nome="Carlos Lima")
    assert p.classe == "comercial"
    assert p.cenario_fatura == "em_dia"
    assert p.n_ucs >= 2
    assert p.outage_ativa is False


def test_canonicos_deterministicos_entre_chamadas() -> None:
    # Idempotência também no caminho canônico (e CPF estável por telefone).
    for nome, tel in (
        ("Ana Souza", ANA_TEL),
        ("Carlos Lima", CARLOS_TEL),
        ("Joana Pereira", JOANA_TEL),
    ):
        a = perfil_de(tel, SEED, nome=nome)
        b = perfil_de(tel, SEED, nome=nome)
        assert a == b
        assert cpf_valido(a.cpf)
        # CPF segue derivado do telefone (igual ao da derivação pura).
        assert a.cpf == perfil_de(tel, SEED).cpf


def test_perfil_rico_garante_cenario_demonstravel() -> None:
    p = perfil_de(EDGAR, SEED, rico=True)
    assert p.cenario_fatura == "uma_vencida"
    assert p.outage_ativa is True
    assert p.bairro == "Jardim das Flores"


def test_multiplos_telefones_cpfs_unicos() -> None:
    phones = [f"55819931121{n:02d}" for n in range(50)]
    cpfs = {perfil_de(p, SEED).cpf for p in phones}
    assert len(cpfs) == len(phones)  # sem colisão de CPF
