"""Testes de integração do seeder (SPEC-006): idempotência + cenário."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from src.application.persona_registry import carregar_personas
from src.infrastructure.orm import (
    ChamadoORM,
    FaturaORM,
    InterrupcaoORM,
    LeituraORM,
    TitularORM,
    UnidadeORM,
)
from src.infrastructure.seed import seed_personas

FIXED_NOW = dt.datetime(2026, 5, 30, 12, tzinfo=dt.UTC)

# Default do .env.example: as 3 canônicas com nome completo.
_DEFAULT = (
    "Ana Souza:555199990001;Carlos Lima:555199990002;Joana Pereira:555199990003"
)


def _count(session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def test_seed_persona_unica_idempotente_e_cenario_rico(session) -> None:
    personas = carregar_personas("Edgar Damasceno:5581993112159", 42)
    _, perfil = personas[0]

    rep = seed_personas(session, personas, history_months=24, now=FIXED_NOW)
    session.flush()

    assert rep.titulares == 1
    assert rep.unidades == perfil.n_ucs
    assert rep.faturas == 24 * perfil.n_ucs
    assert _count(session, LeituraORM) == 24 * perfil.n_ucs

    # Perfil rico (persona única): fatura vencida + outage ativa no bairro.
    assert _count(session, FaturaORM, FaturaORM.status == "vencida") >= 1
    assert _count(session, FaturaORM, FaturaORM.status == "em_aberto") >= 1
    assert (
        _count(
            session,
            InterrupcaoORM,
            InterrupcaoORM.status == "ativa",
            InterrupcaoORM.bairro == perfil.bairro,
        )
        == 1
    )

    # Idempotência: re-rodar no mesmo tx não cria nada novo.
    rep2 = seed_personas(session, personas, history_months=24, now=FIXED_NOW)
    session.flush()
    assert rep2.titulares == 0
    assert rep2.faturas == 0
    assert rep2.interrupcoes == 0
    assert rep2.leituras == 0


def test_seed_varias_personas(session) -> None:
    personas = carregar_personas(
        "Ana:555199990001;Carlos:555199990002;Joana:555199990003", 42
    )
    rep = seed_personas(session, personas, history_months=6, now=FIXED_NOW)
    session.flush()

    assert rep.titulares == 3
    assert _count(session, TitularORM) >= 3
    total_ucs = sum(perfil.n_ucs for _, perfil in personas)
    assert rep.faturas == 6 * total_ucs


def test_seed_multi_uc_cria_varias_unidades_distintas(session) -> None:
    # 5581988880001 deriva 4 UCs (comercial). Seed cria 4 UCs com numero_uc único (SPEC-013).
    personas = carregar_personas("Multi:5581988880001", 42)
    _, perfil = personas[0]
    assert perfil.n_ucs == 4
    rep = seed_personas(session, personas, history_months=6, now=FIXED_NOW)
    session.flush()
    assert rep.unidades == 4
    titular = session.scalar(
        select(TitularORM).where(TitularORM.telefone_principal == "5581988880001")
    )
    numeros = session.scalars(
        select(UnidadeORM.numero_uc).where(UnidadeORM.titular_id == titular.id)
    ).all()
    assert len(numeros) == 4 and len(set(numeros)) == 4  # distintos
    assert rep.faturas == 6 * 4


def test_seed_default_canonico_outage_ana_e_religacao_joana(session) -> None:
    # Com o default (ADR-0011), o seeder materializa os cenários canônicos:
    # interrupção ATIVA no bairro da Ana e chamado de religação da Joana.
    personas = carregar_personas(_DEFAULT, 42)
    perfis = {p.nome: perfil for p, perfil in personas}
    ana, joana = perfis["Ana Souza"], perfis["Joana Pereira"]
    assert ana.bairro == "Jardim das Flores" and ana.outage_ativa is True
    assert joana.classe == "rural" and joana.corte_religacao is True

    rep = seed_personas(session, personas, history_months=6, now=FIXED_NOW)
    session.flush()

    # (a) Interrupção ativa no bairro canônico da Ana.
    assert (
        _count(
            session,
            InterrupcaoORM,
            InterrupcaoORM.status == "ativa",
            InterrupcaoORM.bairro == ana.bairro,
        )
        == 1
    )
    # (b) Chamado de religação da Joana (persona rural).
    joana_tit = session.scalar(
        select(TitularORM).where(TitularORM.telefone_principal == "555199990003")
    )
    assert (
        _count(
            session,
            ChamadoORM,
            ChamadoORM.titular_id == joana_tit.id,
            ChamadoORM.tipo == "religacao",
        )
        == 1
    )
    assert rep.interrupcoes >= 1
    assert rep.chamados >= 1

    # Idempotência: re-rodar não duplica interrupção nem chamado.
    rep2 = seed_personas(session, personas, history_months=6, now=FIXED_NOW)
    session.flush()
    assert rep2.interrupcoes == 0
    assert rep2.chamados == 0
    assert (
        _count(
            session,
            InterrupcaoORM,
            InterrupcaoORM.status == "ativa",
            InterrupcaoORM.bairro == ana.bairro,
        )
        == 1
    )


def test_seed_telefone_resolve_titular(session) -> None:
    personas = carregar_personas("Edgar Damasceno:5581993112159", 42)
    seed_personas(session, personas, history_months=3, now=FIXED_NOW)
    session.flush()
    tit = session.scalar(
        select(TitularORM).where(TitularORM.telefone_principal == "5581993112159")
    )
    assert tit is not None
    assert tit.nome == "Edgar Damasceno"
