"""Testes de integração do seeder (SPEC-006): idempotência + cenário."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from src.application.persona_registry import carregar_personas
from src.infrastructure.orm import FaturaORM, InterrupcaoORM, LeituraORM, TitularORM
from src.infrastructure.seed import seed_personas

FIXED_NOW = dt.datetime(2026, 5, 30, 12, tzinfo=dt.UTC)


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


def test_seed_telefone_resolve_titular(session) -> None:
    personas = carregar_personas("Edgar Damasceno:5581993112159", 42)
    seed_personas(session, personas, history_months=3, now=FIXED_NOW)
    session.flush()
    tit = session.scalar(
        select(TitularORM).where(TitularORM.telefone_principal == "5581993112159")
    )
    assert tit is not None
    assert tit.nome == "Edgar Damasceno"
