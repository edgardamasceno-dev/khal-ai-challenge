"""Ports (interfaces) da aplicacao. Adapters concretos vivem em
infrastructure/. Repository pattern + Unit of Work.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Protocol, runtime_checkable

from src.domain.billing.documento import FaturaDetalhada
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MemoriaConversa
from src.domain.knowledge.entities import ResultadoKB
from src.domain.outage.entities import Interrupcao
from src.domain.ticketing.entities import Chamado, Handoff


@runtime_checkable
class KnowledgeRetrievalPort(Protocol):
    def search(self, query: str, limit: int) -> list[ResultadoKB]: ...


@runtime_checkable
class TitularRepository(Protocol):
    def find_by_phone(self, telefone: str) -> Titular | None: ...
    def get(self, titular_id: uuid.UUID) -> Titular | None: ...
    def list_contratos(self, titular_id: uuid.UUID) -> list[Contrato]: ...


@runtime_checkable
class UnidadeRepository(Protocol):
    def get(self, uc_id: uuid.UUID) -> UnidadeConsumidora | None: ...


@runtime_checkable
class FaturaRepository(Protocol):
    def list_for_unidade(
        self, uc_id: uuid.UUID, status: str | None, limit: int
    ) -> list[Fatura]: ...
    def get(self, fatura_id: uuid.UUID) -> Fatura | None: ...
    def marcar_paga(
        self, fatura_id: uuid.UUID, idempotency_key: str, now: dt.datetime
    ) -> Fatura | None: ...


@runtime_checkable
class InvoicePdfRenderer(Protocol):
    """Renderiza a fatura detalhada em PDF (A4). Adapter: WeasyPrint."""

    def render(self, detalhe: FaturaDetalhada) -> bytes: ...


@runtime_checkable
class ObjectStorage(Protocol):
    """Storage de objetos (S3-compatível). Adapter: MinIO."""

    def exists(self, key: str) -> bool: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def public_url(self, key: str) -> str: ...
    def presigned_url(self, key: str, expires_seconds: int) -> str: ...


@runtime_checkable
class InterrupcaoRepository(Protocol):
    def find_ativa_por_regiao(
        self, bairro: str, cidade: str | None, uf: str | None
    ) -> Interrupcao | None: ...
    def abrir(
        self, bairro: str, cidade: str, uf: str, causa: str | None,
        previsao: dt.datetime | None, now: dt.datetime,
    ) -> Interrupcao: ...
    def encerrar(
        self, bairro: str, cidade: str | None, uf: str | None, now: dt.datetime
    ) -> Interrupcao | None: ...


@runtime_checkable
class ChamadoRepository(Protocol):
    def get_by_protocolo(self, protocolo: str) -> Chamado | None: ...
    def get_by_idempotency_key(self, key: str) -> Chamado | None: ...
    def list_for_titular(self, titular_id: uuid.UUID) -> list[Chamado]: ...
    def add(self, chamado: Chamado, idempotency_key: str) -> Chamado: ...


@runtime_checkable
class HandoffRepository(Protocol):
    def add(self, handoff: Handoff) -> Handoff: ...


@runtime_checkable
class MemoriaRepository(Protocol):
    def list_for_chat(self, chat_id: str) -> list[MemoriaConversa]: ...
    def upsert(self, chat_id: str, chave: str, valor: object) -> MemoriaConversa: ...


@runtime_checkable
class EventBus(Protocol):
    """Publica/consome eventos de domínio (utilitycx.*). Adapter: NATS."""

    def publish(self, subject: str, payload: dict[str, Any]) -> None: ...


@runtime_checkable
class OmniSender(Protocol):
    """Envia texto pelo canal (Omni REST). Best-effort no deliverable."""

    def send_text(self, chat_id: str, texto: str) -> bool: ...


@runtime_checkable
class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
