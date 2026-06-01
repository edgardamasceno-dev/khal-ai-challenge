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

    def invoice_pdf(self, fatura_id: str, presigned: bool = False) -> dict[str, Any]:
        r = self._c.get(f"/invoices/{fatura_id}/pdf", params={"presigned": presigned})
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    def send_invoice(self, fatura_id: str) -> dict[str, Any]:
        r = self._c.post(f"/invoices/{fatura_id}/send")
        r.raise_for_status()
        data: dict[str, Any] = r.json()
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

    def get_conversation_memory(self, chat: str, limit: int = 10) -> list[dict[str, Any]]:
        """Memoria canonica do chat do titular (GET /conversations/{chat}/memory).

        `chat` e o telefone canonico normalizado (chat_id == telefone E.164, ADR-0005).
        Envia `?limit=` por cortesia ao servidor; a truncagem definitiva ocorre no
        CxTools (o router legado pode ignorar o parametro sem quebrar)."""
        r = self._c.get(f"/conversations/{chat}/memory", params={"limit": limit})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    def get_chat_messages(self, phone: str, limit: int = 10) -> list[dict[str, Any]]:
        """Transcricao crua do chat do titular no WhatsApp/Omni (ADR-0013, SPEC-024).

        Reusa o transcript do operador (SPEC-018) via GET /chats/{phone}/messages,
        espelhando o consumo de `get_conversation_memory`. `phone` e o telefone canonico
        do titular (path param); o adapter Omni resolve o chatId pelas variantes do nono
        digito/LID (SPEC-015), nunca por chat citado pelo cliente. Devolve apenas a lista
        de mensagens [{id, texto, do_cliente, em}] (ordem das mais recentes), descartando
        o cursor/tem_mais de paginacao do operador. Best-effort: Omni off -> lista vazia."""
        r = self._c.get(f"/chats/{phone}/messages", params={"limit": limit})
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        mensagens: list[dict[str, Any]] = body.get("mensagens", [])
        return mensagens
