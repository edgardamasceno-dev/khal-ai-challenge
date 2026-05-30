"""Adapter httpx do LegacyApiClient: fala REST com o backend (SPEC-001)."""

from __future__ import annotations

from typing import Any

import httpx

from src.interfaces.mcp.ports import LegacyValidationError


class HttpxLegacyApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._c = httpx.Client(base_url=base_url, timeout=timeout)

    def find_customer(self, phone: str) -> dict[str, Any] | None:
        r = self._c.get("/customers", params={"phone": phone})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def list_contracts(self, titular_id: str) -> list[dict[str, Any]]:
        r = self._c.get(f"/customers/{titular_id}/contracts")
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    def list_invoices(self, uc_id: str) -> list[dict[str, Any]]:
        r = self._c.get(f"/units/{uc_id}/invoices", params={"limit": 24})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    def get_outage(self, bairro: str) -> dict[str, Any]:
        r = self._c.get("/outages", params={"bairro": bairro})
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def create_ticket(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._c.post("/tickets", json=payload)
        if r.status_code == 422:
            raise LegacyValidationError(r.text)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def get_ticket(self, protocolo: str) -> dict[str, Any] | None:
        r = self._c.get(f"/tickets/{protocolo}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._c.post("/handoffs", json=payload)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def search_kb(self, query: str) -> list[dict[str, Any]]:
        r = self._c.get("/kb/search", params={"q": query, "limit": 3})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data
