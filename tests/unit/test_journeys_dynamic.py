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
    )
    for fixo in fixos:
        assert fixo in nomes


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
