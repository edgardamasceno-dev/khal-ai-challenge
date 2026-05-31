"""Testes do endpoint /api/proactive (SPEC-009)."""

from __future__ import annotations

from types import SimpleNamespace

ANA = "555199990001"


def test_candidates_lista_pagamento_e_outage(ctx: SimpleNamespace) -> None:
    r = ctx.client.get("/proactive/candidates", params={"phone": ANA})
    assert r.status_code == 200
    body = r.json()
    assert body["encontrado"] is True
    assert body["pagamentos"]
    assert body["outages"] and body["outages"][0]["bairro"] == "Jardim das Flores"


def test_candidates_desconhecido(ctx: SimpleNamespace) -> None:
    r = ctx.client.get("/proactive/candidates", params={"phone": "550000000000"})
    assert r.json()["encontrado"] is False


def test_emit_event_pagamento(ctx: SimpleNamespace) -> None:
    r = ctx.client.post("/proactive/events", json={
        "phone": ANA, "tipo": "pagamento", "subtipo": "confirmado",
        "dados": {"mes": "05/2026", "valor": "R$ 190,00"},
    })
    assert r.status_code == 202
    body = r.json()
    assert body["subject"] == "utilitycx.pagamento.confirmado"
    assert "Ana" in body["preview"] and "R$ 190,00" in body["preview"]


def test_emit_event_invalido_422(ctx: SimpleNamespace) -> None:
    r = ctx.client.post("/proactive/events", json={
        "phone": ANA, "tipo": "pagamento", "subtipo": "estornado", "dados": {},
    })
    assert r.status_code == 422


def test_emit_event_telefone_desconhecido_404(ctx: SimpleNamespace) -> None:
    r = ctx.client.post("/proactive/events", json={
        "phone": "550000000000", "tipo": "outage", "subtipo": "encerrada",
        "dados": {"bairro": "Centro"},
    })
    assert r.status_code == 404
