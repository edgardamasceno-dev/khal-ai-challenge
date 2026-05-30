"""Entidades do contexto Ticketing & Handoff."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from src.domain.shared.value_objects import TipoChamado


@dataclass(frozen=True)
class Chamado:
    id: uuid.UUID
    protocolo: str
    titular_id: uuid.UUID
    uc_id: uuid.UUID | None
    tipo: TipoChamado
    descricao: str | None
    status: str
    sla_horas: int
    canal: str
    aberto_em: dt.datetime
    atualizado_em: dt.datetime


@dataclass(frozen=True)
class Handoff:
    id: uuid.UUID
    chamado_id: uuid.UUID | None
    motivo: str | None
    status: str
    operador: str | None
    criado_em: dt.datetime
