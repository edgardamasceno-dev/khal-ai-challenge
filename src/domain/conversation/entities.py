"""Entidade do contexto Conversation (memoria curta por chatId)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoriaConversa:
    chat_id: str
    chave: str
    valor: Any
    atualizado_em: dt.datetime


@dataclass(frozen=True)
class MensagemChat:
    """Uma mensagem da conversa no canal (WhatsApp via Omni). SPEC-018."""

    id: str
    texto: str
    do_cliente: bool  # True = recebida do cliente; False = enviada (agente/operador)
    em: dt.datetime
