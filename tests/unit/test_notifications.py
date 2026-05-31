"""Testes do domínio de notificações (SPEC-009): determinismo dos templates."""

from __future__ import annotations

import pytest

from src.domain.notifications.entities import EventoCX
from src.domain.notifications.templates import render_notificacao
from src.domain.shared.errors import InvariantError


def _ev(tipo: str, subtipo: str, **dados: object) -> EventoCX:
    return EventoCX(tipo=tipo, subtipo=subtipo, telefone="5581993112159",
                    nome="Edgar Damasceno", idempotency_key="k1", dados=dados)


def test_evento_invalido() -> None:
    with pytest.raises(InvariantError, match="evento invalido"):
        _ev("pagamento", "estornado")


def test_subject_e_chave() -> None:
    ev = _ev("outage", "encerrada", bairro="Jardim das Flores")
    assert ev.subject == "utilitycx.outage.encerrada"
    assert ev.memoria_chave == "proativo.outage.encerrada"
    assert ev.chat_id == "5581993112159"


def test_pagamento_confirmado_deterministico() -> None:
    ev = _ev("pagamento", "confirmado", mes="05/2026", valor="R$ 268,69")
    txt = render_notificacao(ev)
    assert "Edgar" in txt and "05/2026" in txt and "R$ 268,69" in txt
    assert render_notificacao(ev) == txt  # determinístico


def test_outage_aberta_com_e_sem_previsao() -> None:
    com = render_notificacao(_ev("outage", "aberta", bairro="Centro", previsao="hoje 18h"))
    assert "Centro" in com and "hoje 18h" in com  # texto livre passa direto
    sem = render_notificacao(_ev("outage", "aberta", bairro="Centro"))
    assert "Previsão" not in sem


def test_outage_previsao_iso_vira_formato_amigavel() -> None:
    # ISO (UTC) -> horário de Brasília, formato amigável (não o ISO cru).
    txt = render_notificacao(
        _ev("outage", "aberta", bairro="Centro", previsao="2026-05-31T01:57:13+00:00")
    )
    assert "2026-05-31T01:57:13" not in txt  # nada de ISO cru
    assert "às 22h57" in txt  # 01:57 UTC = 22:57 BRT (dia anterior)


def test_outage_encerrada() -> None:
    txt = render_notificacao(_ev("outage", "encerrada", bairro="Jardim das Flores"))
    assert "normalizado" in txt and "Jardim das Flores" in txt
