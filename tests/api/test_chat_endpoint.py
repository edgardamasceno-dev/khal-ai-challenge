"""API da aba Chat do operador (SPEC-018)."""

from __future__ import annotations

from types import SimpleNamespace

PHONE = "5581993112159"


def test_messages_lista_e_inverte_fromMe(ctx: SimpleNamespace) -> None:
    r = ctx.client.get(f"/chats/{PHONE}/messages?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert [m["texto"] for m in body["mensagens"]] == [
        "Oi, preciso da 2ª via", "Claro! Enviei o PDF.",
    ]
    assert body["mensagens"][0]["do_cliente"] is True
    assert body["mensagens"][1]["do_cliente"] is False


def test_takeover_e_release_alternam_pausa(ctx: SimpleNamespace) -> None:
    assert ctx.client.get(f"/chats/{PHONE}/status").json()["pausado"] is False
    r = ctx.client.post(f"/chats/{PHONE}/takeover")
    assert r.status_code == 200 and r.json()["pausado"] is True
    assert ctx.control.pausados == [PHONE]
    assert ctx.client.get(f"/chats/{PHONE}/status").json()["pausado"] is True
    rel = ctx.client.post(f"/chats/{PHONE}/release")
    assert rel.json()["pausado"] is False and ctx.control.retomados == [PHONE]


def test_send_mensagem(ctx: SimpleNamespace) -> None:
    r = ctx.client.post(f"/chats/{PHONE}/send", json={"texto": "Posso ajudar?"})
    assert r.status_code == 200 and r.json()["enviado"] is True
