"""Adapter de envio de texto pelo Omni (REST). Implementa OmniSender.

Best-effort (ADR-0005): se o Omni não estiver acessível (deliverable sem sandbox),
retorna False e o caso de uso segue gravando a memória (auditável). No sandbox,
`omni_url` aponta para a API real -> envio de WhatsApp.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("proactive.omni")


class HttpxOmniSender:
    def __init__(self, base_url: str, api_key: str = "", timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout

    def send_text(self, chat_id: str, texto: str) -> bool:
        try:
            r = httpx.post(
                f"{self._base}/api/v2/messages/send",
                json={"chatId": chat_id, "text": texto},
                headers=self._headers, timeout=self._timeout,
            )
            r.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning("Omni indisponível, notificação só na memória: %s", exc)
            return False
