"""Presença ("digitando"/typing) e read receipt no Omni sender (R-04, SPEC-031).

Testa `HttpxOmniSender.enviar_presenca` / `marcar_lida` com `httpx.MockTransport`
(sem rede): assert URL + payload + JID resolvido, e a garantia best-effort de que
qualquer falha do Omni vira `False` sem propagar — presença/leitura nunca bloqueiam
o turno do agente (ADR-0018).
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.application.ports import PresencePort
from src.infrastructure.events.omni_sender import HttpxOmniSender

_JID = "558193112159@s.whatsapp.net"


def _sender(handler) -> HttpxOmniSender:  # type: ignore[no-untyped-def]
    """Sender com transport mockado (instância/api_key fixos)."""
    return HttpxOmniSender(
        "http://omni",
        api_key="k",
        instance_id="i1",
        transport=httpx.MockTransport(handler),
    )


def _ok_check_number(request: httpx.Request) -> httpx.Response | None:
    """Resolve o JID no check-number; None para deixar o handler tratar o resto."""
    if request.url.path.endswith("/check-number"):
        return httpx.Response(200, json={"data": [{"exists": True, "jid": _JID}]})
    return None


class TestEnviarPresenca:
    def test_compose_url_payload_e_jid(self) -> None:
        capturado: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            pre = _ok_check_number(request)
            if pre is not None:
                return pre
            capturado["url"] = str(request.url)
            capturado["json"] = json.loads(request.content)
            return httpx.Response(200, json={})

        assert _sender(handler).enviar_presenca("5581993112159") is True
        assert capturado["url"] == "http://omni/api/v2/messages/presence"
        assert capturado["json"] == {
            "instanceId": "i1",
            "to": _JID,
            "presence": "composing",
        }

    def test_estado_explicito_vai_no_payload(self) -> None:
        capturado: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            pre = _ok_check_number(request)
            if pre is not None:
                return pre
            capturado["json"] = json.loads(request.content)
            return httpx.Response(200, json={})

        assert _sender(handler).enviar_presenca("5581993112159", "paused") is True
        assert capturado["json"]["presence"] == "paused"  # type: ignore[index]

    def test_numero_sem_whatsapp_nao_envia(self) -> None:
        chamou_presence = {"v": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/check-number"):
                return httpx.Response(200, json={"data": [{"exists": False}]})
            chamou_presence["v"] = True
            return httpx.Response(200, json={})

        assert _sender(handler).enviar_presenca("5581900000000") is False
        assert chamou_presence["v"] is False  # nem chega a postar a presença

    def test_omni_off_best_effort_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rota")

        assert _sender(handler).enviar_presenca("5581993112159") is False

    def test_erro_http_best_effort_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            pre = _ok_check_number(request)
            if pre is not None:
                return pre
            return httpx.Response(500, json={"error": "boom"})

        assert _sender(handler).enviar_presenca("5581993112159") is False

    def test_sem_instancia_false_sem_rede(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("não deveria tocar a rede sem instance_id")

        sender = HttpxOmniSender(
            "http://omni", instance_id="", transport=httpx.MockTransport(handler)
        )
        assert sender.enviar_presenca("5581993112159") is False


class TestMarcarLida:
    def test_read_url_payload_e_jid(self) -> None:
        capturado: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            pre = _ok_check_number(request)
            if pre is not None:
                return pre
            capturado["url"] = str(request.url)
            capturado["json"] = json.loads(request.content)
            return httpx.Response(200, json={})

        assert _sender(handler).marcar_lida("5581993112159") is True
        assert capturado["url"] == "http://omni/api/v2/messages/read"
        assert capturado["json"] == {"instanceId": "i1", "to": _JID}

    def test_numero_sem_whatsapp_nao_marca(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/check-number"):
                return httpx.Response(200, json={"data": [{"exists": False}]})
            raise AssertionError("não deveria postar read sem JID")

        assert _sender(handler).marcar_lida("5581900000000") is False

    def test_omni_off_best_effort_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rota")

        assert _sender(handler).marcar_lida("5581993112159") is False

    def test_sem_instancia_false_sem_rede(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("não deveria tocar a rede sem instance_id")

        sender = HttpxOmniSender(
            "http://omni", instance_id="", transport=httpx.MockTransport(handler)
        )
        assert sender.marcar_lida("5581993112159") is False


def test_adapter_satisfaz_presence_port() -> None:
    """O adapter REST é, estruturalmente, uma PresencePort (porta segregada ISP)."""
    assert isinstance(HttpxOmniSender("http://omni", instance_id="i1"), PresencePort)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
