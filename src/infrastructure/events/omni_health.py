"""Adapter de saúde do canal Omni: WhatsApp (instância Baileys) e Agente.

- WhatsApp: `GET /api/v2/instances/{id}/status` -> `data.isConnected`.
- Agente:   `GET /api/v2/agents` -> o agente da instância (`agentId`) está `isActive`.

Best-effort (SPEC-014): Omni inacessível / sem instância -> 'unknown'.
Implementa `ChannelHealthPort`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.infrastructure.events.omni_instances import resolve_instance_id

logger = logging.getLogger("health.omni")


class HttpxOmniHealth:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        instance_id: str = "",
        instance_name: str = "",
        timeout: float = 2.5,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._instance_id = instance_id
        self._instance_name = instance_name  # SPEC-030: resolve o id por nome se vazio
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout

    def _eid(self) -> str:
        """Instance-id efetivo: fixo ou resolvido pelo nome (SPEC-030); lazy + cacheado."""
        if not self._instance_id and self._instance_name:
            self._instance_id = (
                resolve_instance_id(self._base, self._headers, self._instance_name) or ""
            )
        return self._instance_id

    def _get(self, client: httpx.Client, path: str) -> Any:
        r = client.get(f"{self._base}{path}")
        r.raise_for_status()
        return r.json()

    def whatsapp(self) -> str:
        if not self._eid():
            return "unknown"
        try:
            with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
                data = self._get(client, f"/api/v2/instances/{self._instance_id}/status").get(
                    "data", {}
                )
            return "ok" if data.get("isConnected") else "down"
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("status WhatsApp indisponível: %s", exc)
            return "unknown"

    def _agent_id(self, client: httpx.Client) -> str | None:
        data = self._get(client, f"/api/v2/instances/{self._instance_id}").get("data", {})
        agent_id: str | None = data.get("agentId")
        return agent_id

    def agente(self) -> str:
        if not self._eid():
            return "unknown"
        try:
            with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
                agent_id = self._agent_id(client)
                if not agent_id:
                    return "down"
                items = self._get(client, "/api/v2/agents").get("items", [])
            for a in items:
                if a.get("id") == agent_id:
                    return "ok" if a.get("isActive") else "down"
            return "down"
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("status Agente indisponível: %s", exc)
            return "unknown"
