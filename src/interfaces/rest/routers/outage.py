"""Outage: status de interrupcao por regiao. Alimenta get_outage_by_region."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.application.services import OutageService
from src.interfaces.rest.dependencies import get_outage_service
from src.interfaces.rest.schemas import OutageDTO, OutageQueryResultDTO

router = APIRouter(tags=["outage"])


@router.get("/outages", response_model=OutageQueryResultDTO)
def get_outage_by_region(
    bairro: str = Query(..., description="Bairro da UC do cliente"),
    cidade: str | None = Query(None),
    uf: str | None = Query(None, min_length=2, max_length=2),
    svc: OutageService = Depends(get_outage_service),
) -> OutageQueryResultDTO:
    interrupcao = svc.find_active_by_region(bairro, cidade, uf)
    if interrupcao is None:
        return OutageQueryResultDTO(encontrada=False, interrupcao=None)
    return OutageQueryResultDTO(encontrada=True, interrupcao=OutageDTO.from_entity(interrupcao))
