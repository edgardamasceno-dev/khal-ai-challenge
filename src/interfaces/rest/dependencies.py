"""Composition root da borda HTTP: sessao -> repositorios -> serviços
via FastAPI Depends.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.services import (
    BillingService,
    MemoryService,
    OutageService,
    TicketingService,
)
from src.infrastructure.db import SessionLocal
from src.infrastructure.repositories import (
    SqlAlchemyUnitOfWork,
    SqlChamadoRepository,
    SqlFaturaRepository,
    SqlHandoffRepository,
    SqlInterrupcaoRepository,
    SqlMemoriaRepository,
    SqlTitularRepository,
    SqlUnidadeRepository,
)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_billing_service(session: Session = Depends(get_session)) -> BillingService:
    return BillingService(
        SqlTitularRepository(session),
        SqlUnidadeRepository(session),
        SqlFaturaRepository(session),
    )


def get_outage_service(session: Session = Depends(get_session)) -> OutageService:
    return OutageService(SqlInterrupcaoRepository(session))


def get_ticketing_service(session: Session = Depends(get_session)) -> TicketingService:
    return TicketingService(
        SqlChamadoRepository(session),
        SqlHandoffRepository(session),
        SqlTitularRepository(session),
        SqlAlchemyUnitOfWork(session),
    )


def get_memory_service(session: Session = Depends(get_session)) -> MemoryService:
    return MemoryService(SqlMemoriaRepository(session), SqlAlchemyUnitOfWork(session))
