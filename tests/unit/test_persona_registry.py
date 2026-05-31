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


def test_default_canonico_produz_cenarios_canonicos() -> None:
    # O default do .env.example (3 canônicas) entrega os cenários FIXOS que a
    # demo e os evals esperam (ADR-0011), via o nome -> persona_key.
    res = carregar_personas(
        "Ana Souza:555199990001;Carlos Lima:555199990002;Joana Pereira:555199990003", 42
    )
    por_nome = {p.nome: perfil for p, perfil in res}
    ana = por_nome["Ana Souza"]
    assert ana.bairro == "Jardim das Flores"
    assert ana.cenario_fatura == "uma_vencida"
    assert ana.outage_ativa is True
    carlos = por_nome["Carlos Lima"]
    assert carlos.classe == "comercial"
    assert carlos.n_ucs >= 2
    assert carlos.cenario_fatura == "em_dia"
    joana = por_nome["Joana Pereira"]
    assert joana.classe == "rural"
    assert joana.corte_religacao is True


def test_persona_unica_canonica_recebe_canonico_nao_rico() -> None:
    # Precedência canônico > rico: Carlos sozinho mantém o cenário comercial
    # (não é forçado ao perfil rico residencial+outage).
    [(_, perfil)] = carregar_personas("Carlos Lima:555199990002", 42)
    assert perfil.classe == "comercial"
    assert perfil.cenario_fatura == "em_dia"
    assert perfil.outage_ativa is False
