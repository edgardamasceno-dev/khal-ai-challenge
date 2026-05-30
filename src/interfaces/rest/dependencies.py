"""Composition root da borda HTTP: sessao -> repositorios -> serviços
via FastAPI Depends.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.ports import KnowledgeRetrievalPort
from src.application.services import (
    BillingService,
    MemoryService,
    OutageService,
    TicketingService,
)
from src.config import settings
from src.infrastructure.db import SessionLocal
from src.infrastructure.knowledge import FilesystemKnowledgeRetrieval
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


@lru_cache(maxsize=1)
def _knowledge_retrieval() -> FilesystemKnowledgeRetrieval:
    # Carrega o kb/ uma unica vez (Strategy filesystem, ADR-0004).
    return FilesystemKnowledgeRetrieval(pathlib.Path(settings.kb_dir))


def get_knowledge_retrieval() -> KnowledgeRetrievalPort:
    return _knowledge_retrieval()


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
