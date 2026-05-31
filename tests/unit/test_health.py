"""Testes do HealthService e do adapter HttpxOmniHealth (SPEC-014)."""

from __future__ import annotations

import httpx

from src.application.services import HealthService
from src.infrastructure.events.omni_health import HttpxOmniHealth

INST = "inst-1"


class _FakeChannel:
    def __init__(self, wa: str = "ok", ag: str = "ok") -> None:
        self._wa, self._ag = wa, ag

    def whatsapp(self) -> str:
        return self._wa

    def agente(self) -> str:
        return self._ag


class TestHealthService:
    def test_todos_ok(self) -> None:
        r = HealthService(_FakeChannel()).check(db_ok=True)
        assert r.status == "ok"
        assert {n for n, _ in r.components} == {"api", "whatsapp", "agente"}

    def test_db_down_degrada(self) -> None:
        r = HealthService(_FakeChannel()).check(db_ok=False)
        assert r.status == "degraded" and r.db == "down"

    def test_whatsapp_down_degrada(self) -> None:
        assert HealthService(_FakeChannel(wa="down")).check(db_ok=True).status == "degraded"

    def test_agente_unknown_degrada(self) -> None:
        assert HealthService(_FakeChannel(ag="unknown")).check(db_ok=True).status == "degraded"


def _health_com(handler) -> HttpxOmniHealth:  # type: ignore[no-untyped-def]
    h = HttpxOmniHealth("http://omni", api_key="k", instance_id=INST)
    h._get = lambda client, path: handler(path)  # type: ignore[assignment,method-assign]
    return h


class TestHttpxOmniHealth:
    def test_sem_instancia_unknown(self) -> None:
        h = HttpxOmniHealth("http://omni", instance_id="")
        assert h.whatsapp() == "unknown" and h.agente() == "unknown"

    def test_whatsapp_conectado(self) -> None:
        h = _health_com(lambda path: {"data": {"isConnected": True}})
        assert h.whatsapp() == "ok"

    def test_whatsapp_desconectado(self) -> None:
        h = _health_com(lambda path: {"data": {"isConnected": False}})
        assert h.whatsapp() == "down"

    def test_agente_ativo(self) -> None:
        def handler(path: str) -> dict:  # type: ignore[type-arg]
            if path.endswith(f"/instances/{INST}"):
                return {"data": {"agentId": "a1"}}
            return {"items": [{"id": "a1", "isActive": True}]}

        assert _health_com(handler).agente() == "ok"

    def test_agente_inativo(self) -> None:
        def handler(path: str) -> dict:  # type: ignore[type-arg]
            if path.endswith(f"/instances/{INST}"):
                return {"data": {"agentId": "a1"}}
            return {"items": [{"id": "a1", "isActive": False}]}

        assert _health_com(handler).agente() == "down"

    def test_omni_inacessivel_unknown(self) -> None:
        def boom(path: str) -> dict:  # type: ignore[type-arg]
            raise httpx.ConnectError("sem rota")

        h = _health_com(boom)
        assert h.whatsapp() == "unknown" and h.agente() == "unknown"
