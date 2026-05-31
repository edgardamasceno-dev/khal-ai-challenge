"""Adapter de diretório de chats do Omni (SPEC-015): resolve LID -> telefone.

O Omni mapeia, em `GET /api/v2/chats`, o `externalId` (`<lid>@lid`) ao `canonicalId`
(`<msisdn>@s.whatsapp.net`). Devolve o telefone canônico (só dígitos) do chat cujo
`externalId` casa com o id recebido. Best-effort: Omni inacessível -> None.
Implementa `ChatDirectoryPort`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.domain.shared.phone import normalizar_msisdn

logger = logging.getLogger("directory.omni")


class HttpxOmniChats:
    def __init__(
        self, base_url: str, api_key: str = "", instance_id: str = "", timeout: float = 3.0
    ) -> None:
        self._base = base_url.rstrip("/")
        self._instance_id = instance_id
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout

    def _fetch_chats(self) -> list[dict[str, Any]]:
        with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
            r = client.get(
                f"{self._base}/api/v2/chats", params={"instanceId": self._instance_id}
            )
            r.raise_for_status()
            items: list[dict[str, Any]] = r.json().get("items", [])
            return items

    def resolve_canonical(self, external_id: str) -> str | None:
        if not self._instance_id or not external_id:
            return None
        alvo = normalizar_msisdn(external_id)
        try:
            itens = self._fetch_chats()
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("diretório de chats indisponível: %s", exc)
            return None
        for chat in itens:
            if normalizar_msisdn(chat.get("externalId", "")) == alvo:
                return normalizar_msisdn(chat.get("canonicalId", "")) or None
        return None
