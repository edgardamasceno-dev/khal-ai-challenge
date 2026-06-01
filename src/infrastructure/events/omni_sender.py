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

from src.infrastructure.events.omni_instances import resolve_instance_id

logger = logging.getLogger("proactive.omni")

# Presença é um sinal de UX, não de entrega: timeout bem mais curto que o texto;
# se o Omni demora para confirmar o "digitando", não vale segurar o turno.
_PRESENCE_TIMEOUT = 3.0


class HttpxOmniSender:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        instance_id: str = "",
        instance_name: str = "",
        timeout: float = 8.0,
        media_timeout: float = 12.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._instance_id = instance_id
        self._instance_name = instance_name  # SPEC-030: resolve o id por nome se vazio
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._media_timeout = media_timeout  # anexo é best-effort; não trava o agente
        self._transport = transport  # injetável só em teste (httpx.MockTransport)

    def _eid(self) -> str:
        """Instance-id efetivo: o fixo (OMNI_INSTANCE_ID) ou resolvido pelo nome (SPEC-030).
        Lazy + cacheado: a 1ª resolução bem-sucedida fica em ``self._instance_id``."""
        if not self._instance_id and self._instance_name:
            self._instance_id = (
                resolve_instance_id(
                    self._base, self._headers, self._instance_name, transport=self._transport
                )
                or ""
            )
        return self._instance_id

    def _client(self, timeout: float) -> httpx.Client:
        """Cria o client REST (headers + timeout). O `transport` injetado permite
        testar com `httpx.MockTransport` sem tocar a rede; em produção é None."""
        kwargs: dict[str, object] = {"headers": self._headers, "timeout": timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)  # type: ignore[arg-type]

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
        if not self._eid():
            logger.warning("OMNI_INSTANCE_ID ausente; notificação só na memória.")
            return False
        try:
            with self._client(self._timeout) as client:
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

        **Best-effort com timeout curto**: o upload de mídia do WhatsApp (CDNs
        `*.cdn.whatsapp.net`) pode falhar em ambiente de egress restrito — nesse caso
        não bloqueia o atendimento; o link no texto é o canal confiável. base64 (não
        URL) porque o Omni não alcança o MinIO local.
        """
        if not self._eid():
            return False
        try:
            with self._client(self._media_timeout) as client:
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

    # --- PresencePort: "digitando"/typing + read receipt (R-04, ADR-0018) -------- #

    def enviar_presenca(self, chat_id: str, estado: str = "composing") -> bool:
        """Publica o chat-state do agente no chat (typing/"digitando").

        Mapeia para `POST /api/v2/messages/presence {instanceId, to: <jid>, presence}`
        (Baileys `sendPresenceUpdate`). `estado`: 'composing' (digitando) | 'paused'
        (parou de digitar) | 'available' (online). Resolve o JID canônico igual ao
        `send_text` (onWhatsApp). Best-effort com timeout curto: presença é UX, nunca
        bloqueia o turno — Omni off / endpoint ausente -> False.
        """
        if not self._eid():
            return False
        try:
            with self._client(_PRESENCE_TIMEOUT) as client:
                jid = self._resolve_jid(client, chat_id)
                if jid is None:
                    return False
                r = client.post(
                    f"{self._base}/api/v2/messages/presence",
                    json={
                        "instanceId": self._instance_id,
                        "to": jid,
                        "presence": estado,
                    },
                )
                r.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("Presença (%s) não enviada para %s: %s", estado, chat_id, exc)
            return False

    def marcar_lida(self, chat_id: str) -> bool:
        """Marca como lidas as mensagens do chat (read receipt / markRead).

        Mapeia para `POST /api/v2/messages/read {instanceId, to: <jid>}` (Baileys
        `readMessages`). Resolve o JID igual ao `send_text`. Best-effort com timeout
        curto: o tique azul é cosmético, nunca bloqueia o atendimento.
        """
        if not self._eid():
            return False
        try:
            with self._client(_PRESENCE_TIMEOUT) as client:
                jid = self._resolve_jid(client, chat_id)
                if jid is None:
                    return False
                r = client.post(
                    f"{self._base}/api/v2/messages/read",
                    json={"instanceId": self._instance_id, "to": jid},
                )
                r.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.info("Read receipt não enviado para %s: %s", chat_id, exc)
            return False
