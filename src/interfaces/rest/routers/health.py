from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from src.application.services import HealthService
from src.interfaces.rest.dependencies import get_health_service, get_session
from src.interfaces.rest.schemas import ComponentHealthDTO, HealthDTO

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthDTO)
def health(
    session: Any = Depends(get_session),
    svc: HealthService = Depends(get_health_service),
) -> HealthDTO:
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    r = svc.check(db_ok)
    return HealthDTO(
        status=r.status,
        db=r.db,
        components=[ComponentHealthDTO(name=n, status=s) for n, s in r.components],
    )
