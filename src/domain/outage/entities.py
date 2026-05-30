"""Entidade do contexto Outage (interrupcao de fornecimento)."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Interrupcao:
    id: uuid.UUID
    bairro: str
    cidade: str
    uf: str
    tipo: str
    causa: str | None
    inicio: dt.datetime
    previsao_retorno: dt.datetime | None
    status: str
