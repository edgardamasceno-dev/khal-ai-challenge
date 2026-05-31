"""Notificações proativas (SPEC-009): candidatos + disparo de evento pelo operador.

O disparo publica um evento `utilitycx.*` (consumido pelo worker, ADR-0005).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.application.services import ProactiveService
from src.interfaces.rest.dependencies import get_proactive_service

router = APIRouter(tags=["proactive"], prefix="/proactive")


class ProactiveEventReq(BaseModel):
    phone: str
    tipo: str = Field(description="pagamento | outage")
    subtipo: str = Field(description="confirmado | aberta | encerrada")
    dados: dict[str, Any] = Field(default_factory=dict)


@router.get("/candidates")
def candidates(
    phone: str = Query(..., description="Telefone do cliente (E.164)"),
    svc: ProactiveService = Depends(get_proactive_service),
) -> dict[str, Any]:
    return svc.candidatos(phone)


@router.post("/events", status_code=202)
def emit_event(
    req: ProactiveEventReq,
    svc: ProactiveService = Depends(get_proactive_service),
) -> dict[str, Any]:
    """Dispara o evento (publica em utilitycx.*) e devolve o preview determinístico."""
    return svc.disparar_por_telefone(req.phone, req.tipo, req.subtipo, req.dados)
