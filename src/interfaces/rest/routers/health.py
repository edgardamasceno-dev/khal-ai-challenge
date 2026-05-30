from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from src.interfaces.rest.dependencies import get_session
from src.interfaces.rest.schemas import HealthDTO

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthDTO)
def health(session: Any = Depends(get_session)) -> HealthDTO:
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:
        db = "down"
    return HealthDTO(status="ok" if db == "ok" else "degraded", db=db)
