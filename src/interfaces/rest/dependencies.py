"""Composition root da borda HTTP: sessao -> repositorios -> serviços
via FastAPI Depends.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from src.application.ports import KnowledgeRetrievalPort, ObjectStorage
from src.application.services import (
    BillingService,
    InvoiceDocumentService,
    MemoryService,
    OutageService,
    ProactiveService,
    TicketingService,
)
from src.config import settings
from src.infrastructure.db import SessionLocal
from src.infrastructure.events.nats_bus import NatsEventBus
from src.infrastructure.events.omni_sender import HttpxOmniSender
from src.infrastructure.knowledge import FilesystemKnowledgeRetrieval
from src.infrastructure.pdf.weasyprint_renderer import WeasyPrintInvoiceRenderer
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
from src.infrastructure.storage.minio_storage import MinioObjectStorage


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


@lru_cache(maxsize=1)
def _object_storage() -> ObjectStorage:
    # Conexão única ao MinIO (cria o bucket no boot — ADR-0009).
    return MinioObjectStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket,
        public_base_url=settings.files_public_base_url,
        secure=settings.minio_secure,
    )


def get_invoice_document_service(
    session: Session = Depends(get_session),
) -> InvoiceDocumentService:
    return InvoiceDocumentService(
        faturas=SqlFaturaRepository(session),
        unidades=SqlUnidadeRepository(session),
        titulares=SqlTitularRepository(session),
        renderer=WeasyPrintInvoiceRenderer(),
        storage=_object_storage(),
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


def get_proactive_service(session: Session = Depends(get_session)) -> ProactiveService:
    return ProactiveService(
        NatsEventBus(settings.nats_url),
        HttpxOmniSender(settings.omni_url, settings.omni_api_key),
        SqlMemoriaRepository(session),
        SqlTitularRepository(session),
        SqlFaturaRepository(session),
        SqlInterrupcaoRepository(session),
        SqlAlchemyUnitOfWork(session),
    )
