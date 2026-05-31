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

from src.domain.shared.phone import normalizar_msisdn, variantes_nono_digito

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

    # --- ChannelControlPort: pausar/retomar a IA por conversa (SPEC-016) --------- #

    def _chat_id(self, remetente: str) -> str | None:
        """Id do chat (UUID Omni) casando o remetente por externalId ou canonicalId
        (tolerando o nono dígito no canonical)."""
        alvo = normalizar_msisdn(remetente)
        variantes = set(variantes_nono_digito(alvo))
        for chat in self._fetch_chats():
            ext = normalizar_msisdn(chat.get("externalId", ""))
            can = normalizar_msisdn(chat.get("canonicalId", ""))
            if ext == alvo or ext in variantes or can in variantes:
                cid: str | None = chat.get("id")
                return cid
        return None

    def _set_paused(self, remetente: str, paused: bool) -> bool:
        if not self._instance_id or not remetente:
            return False
        try:
            chat_id = self._chat_id(remetente)
            if not chat_id:
                return False
            with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
                r = client.patch(
                    f"{self._base}/api/v2/chats/{chat_id}",
                    json={"settings": {"agentPaused": paused}},
                )
                r.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("controle do agente indisponível (%s): %s", remetente, exc)
            return False

    def pausar_agente(self, remetente: str) -> bool:
        return self._set_paused(remetente, True)

    def retomar_agente(self, remetente: str) -> bool:
        return self._set_paused(remetente, False)
