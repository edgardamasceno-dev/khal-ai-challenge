"""Testes do registry de personas (SPEC-006): parsing de SEED_PERSONAS."""

from __future__ import annotations

import pytest

from src.application.persona_registry import carregar_personas, parse_personas


def test_uma_persona() -> None:
    [p] = parse_personas("Edgar Damasceno:5581993112159")
    assert p.nome == "Edgar Damasceno"
    assert p.telefone == "5581993112159"


def test_varias_personas_com_espacos() -> None:
    ps = parse_personas(
        " Ana Souza:555199990001 ; Carlos Lima:555199990002 ;Joana Pereira:555199990003 "
    )
    assert [p.nome for p in ps] == ["Ana Souza", "Carlos Lima", "Joana Pereira"]
    assert ps[2].telefone == "555199990003"


def test_ignora_entradas_vazias() -> None:
    ps = parse_personas("Ana:555199990001;;")
    assert len(ps) == 1


def test_vazio_eh_erro() -> None:
    with pytest.raises(ValueError, match="vazio"):
        parse_personas("   ")


def test_sem_telefone_eh_erro() -> None:
    with pytest.raises(ValueError, match="invalida"):
        parse_personas("Só o nome")


def test_telefone_invalido_eh_erro() -> None:
    with pytest.raises(ValueError, match="telefone invalido"):
        parse_personas("Ana:123")


def test_telefone_duplicado_eh_erro() -> None:
    with pytest.raises(ValueError, match="duplicado"):
        parse_personas("Ana:555199990001;Outra:555199990001")


def test_persona_unica_recebe_perfil_rico() -> None:
    [(_, perfil)] = carregar_personas("Edgar:5581993112159", 42)
    assert perfil.cenario_fatura == "uma_vencida"
    assert perfil.outage_ativa is True


def test_multiplas_personas_perfis_derivados() -> None:
    res = carregar_personas("Ana:555199990001;Carlos:555199990002", 42)
    assert len(res) == 2
    # 2+ personas -> perfis puramente derivados (não forçados a rico)
    assert {p.telefone for p, _ in res} == {"555199990001", "555199990002"}
