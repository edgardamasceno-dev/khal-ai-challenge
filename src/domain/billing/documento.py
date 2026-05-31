"""View de leitura para o documento da fatura (SPEC-008)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from src.domain.billing.entities import Fatura, Titular, UnidadeConsumidora


@dataclass(frozen=True)
class FaturaDetalhada:
    """Tudo que o PDF da fatura precisa: titular + UC + fatura + histórico."""

    titular: Titular
    unidade: UnidadeConsumidora
    fatura: Fatura
    historico: list[tuple[str, int]] = field(default_factory=list)  # (mes_ref, kwh)
    emitida_em: dt.date | None = None


@dataclass(frozen=True)
class DocumentoFatura:
    """Resultado de `obter_ou_gerar`: a URL (estável ou pré-assinada)."""

    url: str
    presigned: bool
    expires_at: dt.datetime | None = None
    gerado_agora: bool = False  # False quando veio do storage (não re-renderizou)
