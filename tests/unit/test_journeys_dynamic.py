"""Testes do builder dinâmico de jornadas (SPEC-006)."""

from __future__ import annotations

from src.application.persona_registry import carregar_personas
from src.evals.journeys import build_scenarios


def _names(scenarios) -> list[str]:
    return [s.name for s in scenarios]


def test_persona_unica_gera_jornadas_e_usa_seu_telefone() -> None:
    personas = carregar_personas("Edgar Damasceno:5581993112159", 42)
    scs = build_scenarios(personas)
    # persona única é rica -> tem outage -> J1 e J2 gerados pra ela
    assert any(s.name.startswith("J1-segunda-via[5581993112159]") for s in scs)
    assert any(s.name.startswith("J2-falta-energia[5581993112159]") for s in scs)
    # casos comportamentais usam o telefone da persona primária
    j7 = next(s for s in scs if s.name == "J7-handoff")
    assert j7.phone == "5581993112159"


def test_cross_access_usa_outra_persona_quando_existe() -> None:
    personas = carregar_personas("Ana:555199990001;Carlos:555199990002", 42)
    scs = build_scenarios(personas)
    cross = next(s for s in scs if s.name == "J6b-acesso-cruzado")
    assert "555199990002" in cross.message  # telefone do Carlos referenciado


def test_cliente_desconhecido_fora_do_registry() -> None:
    personas = carregar_personas("Edgar:5581993112159", 42)
    scs = build_scenarios(personas)
    desc = next(s for s in scs if s.name == "cliente-desconhecido")
    assert desc.phone not in {p.telefone for p, _ in personas}


def test_cobre_jornadas_comportamentais_fixas() -> None:
    personas = carregar_personas("Ana:555199990001", 42)
    nomes = _names(build_scenarios(personas))
    fixos = (
        "J3a-pede-confirmacao", "J3b-confirmado", "J6a-injection",
        "J7-handoff", "J8-base-conhecimento",
        # Casos comportamentais fixos na persona primaria (R-03 / M-02 / ADR-0013).
        "J10-eventos-conta", "J10b-eventos-nao-reabre", "J13-tool-erro",
        "J14-transcricao-historico",
    )
    for fixo in fixos:
        assert fixo in nomes


def test_j9_pdf_gerado_para_persona_com_fatura() -> None:
    # Ana (canonica): fatura vencida -> J9 (2a via do PDF) data-driven. R-02.
    personas = carregar_personas("Ana Souza:555199990001", 42)
    ana = next(perfil for p, perfil in personas if p.nome == "Ana Souza")
    assert ana.cenario_fatura in ("uma_aberta", "uma_vencida")
    scs = build_scenarios(personas)
    assert any(s.name.startswith("J9-segunda-via-pdf[555199990001]") for s in scs)


def test_j9_pdf_nao_gerado_para_persona_em_dia() -> None:
    # Carlos (canonico): fatura em dia -> sem J9 (espelha o data-driven de J1/J2).
    personas = carregar_personas("Carlos Lima:555199990002", 42)
    carlos = next(perfil for p, perfil in personas if p.nome == "Carlos Lima")
    assert carlos.cenario_fatura == "em_dia"
    scs = build_scenarios(personas)
    assert not any(s.name.startswith("J9-segunda-via-pdf[") for s in scs)


def test_j11_boas_vindas_para_persona_com_outage() -> None:
    # Ana (canonica): outage ativa -> J11 (boas-vindas no 1o turno). R-11.
    personas = carregar_personas("Ana Souza:555199990001", 42)
    scs = build_scenarios(personas)
    j11 = next(s for s in scs if s.name.startswith("J11-boas-vindas[555199990001]"))
    assert j11.phone == "555199990001"


def test_j12_ambiguo_so_para_multi_uc() -> None:
    # Carlos (canonico): comercial multi-UC (n_ucs>=2) -> J12 (pedido ambiguo). M-02.
    personas = carregar_personas("Carlos Lima:555199990002", 42)
    carlos = next(perfil for p, perfil in personas if p.nome == "Carlos Lima")
    assert carlos.n_ucs >= 2
    scs = build_scenarios(personas)
    assert any(s.name.startswith("J12-ambiguo[555199990002]") for s in scs)


def test_j12_ambiguo_ausente_para_uc_unica() -> None:
    # Joana (canonica): rural, tende a 1 UC -> sem J12 quando n_ucs == 1.
    personas = carregar_personas("Joana Pereira:555199990003", 42)
    joana = next(perfil for p, perfil in personas if p.nome == "Joana Pereira")
    scs = build_scenarios(personas)
    if joana.n_ucs == 1:
        assert not any(s.name.startswith("J12-ambiguo[") for s in scs)
    else:  # pragma: no cover - guarda p/ derivacao futura
        assert any(s.name.startswith("J12-ambiguo[") for s in scs)


# Default do .env.example: as 3 canônicas com nome completo.
_DEFAULT = (
    "Ana Souza:555199990001;Carlos Lima:555199990002;Joana Pereira:555199990003"
)


def test_default_emite_j2_para_a_persona_canonica_de_outage() -> None:
    # Com o default (ADR-0011), Ana tem outage_ativa=True FIXO: a suíte sempre
    # gera a jornada J2 (falta de energia) — não depende mais de sorte.
    personas = carregar_personas(_DEFAULT, 42)
    scs = build_scenarios(personas)
    j2 = [s for s in scs if s.name.startswith("J2-falta-energia[")]
    assert len(j2) >= 1

    # A persona de outage é a Ana (telefone canônico) e o bairro citado na
    # mensagem casa com o bairro do perfil dela ("Jardim das Flores").
    ana = next(perfil for p, perfil in personas if p.nome == "Ana Souza")
    ana_tel = next(p.telefone for p, _ in personas if p.nome == "Ana Souza")
    cenario_ana = next(s for s in j2 if ana_tel in s.name)
    assert cenario_ana.phone == ana_tel
    assert ana.bairro in cenario_ana.message
    assert ana.bairro == "Jardim das Flores"
