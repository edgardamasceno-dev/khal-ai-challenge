"""Adapter de envio de texto pelo Omni (REST). Implementa OmniSender.

Fluxo robusto (sem LID nem 9º dígito no `.env`):
  1. `POST /instances/{id}/check-number {phones:[telefone]}` (Baileys onWhatsApp)
     -> valida se o número tem WhatsApp e devolve o **JID canônico** (resolve
     com/sem 9). Se não tiver conta, não envia.
  2. `POST /api/v2/messages/send {instanceId, to: <jid>, text}` (+ Bearer).

Best-effort (ADR-0005): qualquer falha -> retorna False; a memória já foi gravada
pelo caso de uso (notificação auditável).
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger("proactive.omni")


class HttpxOmniSender:
    def __init__(
        self, base_url: str, api_key: str = "", instance_id: str = "", timeout: float = 8.0
    ) -> None:
        self._base = base_url.rstrip("/")
        self._instance_id = instance_id
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout

    def _resolve_jid(self, client: httpx.Client, telefone: str) -> str | None:
        """Resolve o JID canônico via onWhatsApp; None se o número não tem conta."""
        r = client.post(
            f"{self._base}/api/v2/instances/{self._instance_id}/check-number",
            json={"phones": [telefone]},
        )
        r.raise_for_status()
        results = r.json().get("data", r.json())
        if isinstance(results, dict):
            results = results.get("results", [])
        for item in results:
            if item.get("exists"):
                jid: str | None = item.get("jid")
                return jid
        return None

    def send_text(self, chat_id: str, texto: str) -> bool:
        if not self._instance_id:
            logger.warning("OMNI_INSTANCE_ID ausente; notificação só na memória.")
            return False
        try:
            with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
                jid = self._resolve_jid(client, chat_id)
                if jid is None:
                    logger.info("Telefone %s não tem WhatsApp; só memória.", chat_id)
                    return False
                r = client.post(
                    f"{self._base}/api/v2/messages/send",
                    json={"instanceId": self._instance_id, "to": jid, "text": texto},
                )
                r.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning("Omni indisponível, notificação só na memória: %s", exc)
            return False

    def send_document(
        self, chat_id: str, conteudo: bytes, filename: str, caption: str = ""
    ) -> bool:
        """Envia um PDF como documento anexo (base64) via Omni send/media (ADR-0003).

        base64 (não URL): o Omni baixa a URL server-side e não alcança o MinIO local.
        Best-effort: sem instância / Omni indisponível / sem WhatsApp -> False.
        """
        if not self._instance_id:
            return False
        try:
            with httpx.Client(headers=self._headers, timeout=max(self._timeout, 20.0)) as client:
                jid = self._resolve_jid(client, chat_id)
                if jid is None:
                    logger.info("Telefone %s não tem WhatsApp; anexo não enviado.", chat_id)
                    return False
                r = client.post(
                    f"{self._base}/api/v2/messages/send/media",
                    json={
                        "instanceId": self._instance_id,
                        "to": jid,
                        "type": "document",
                        "base64": base64.b64encode(conteudo).decode(),
                        "filename": filename,
                        "mimeType": "application/pdf",
                        "caption": caption,
                    },
                )
                r.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning("Falha ao enviar anexo pelo Omni: %s", exc)
            return False
