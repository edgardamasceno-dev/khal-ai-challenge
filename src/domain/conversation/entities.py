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
