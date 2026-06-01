"""Conversation: memória de conversa. Chave lógica primária = titular_id (R-12 /
SPEC-027). A borda REST mantém a MESMA URL `/conversations/{chat}/memory` e o MESMO
contrato MCP-over-REST; internamente resolve telefone -> titular e lê por titular,
sem quebrar `get_account_events` (a tool MCP segue imutável). Ver ADR-0013."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from src.application.services import BillingService, MemoryService
from src.domain.shared.errors import NotFoundError
from src.interfaces.rest.dependencies import get_billing_service, get_memory_service
from src.interfaces.rest.schemas import MemoryItemDTO, MemoryPutRequest

router = APIRouter(tags=["conversation"])


def _resolver_titular(billing: BillingService, chat_id: str) -> uuid.UUID | None:
    """LID/telefone do chat -> titular_id (tolerante ao 9º dígito/LID, SPEC-015).
    Chat desconhecido -> None (a leitura cai no fallback puro por chat_id)."""
    try:
        return billing.find_customer_by_phone(chat_id).id
    except NotFoundError:
        return None


@router.get("/conversations/{chat_id}/memory", response_model=list[MemoryItemDTO])
def get_memory(
    chat_id: str,
    svc: MemoryService = Depends(get_memory_service),
    billing: BillingService = Depends(get_billing_service),
) -> list[MemoryItemDTO]:
    # R-12: união (titular + chat) deduplicada quando o titular resolve; senão,
    # fallback puro por chat_id (comportamento legado, cliente desconhecido).
    titular_id = _resolver_titular(billing, chat_id)
    itens = svc.get_unificado(chat_id, titular_id)
    return [MemoryItemDTO.from_entity(m) for m in itens]


@router.put("/conversations/{chat_id}/memory", response_model=MemoryItemDTO)
def put_memory(
    chat_id: str,
    body: MemoryPutRequest,
    svc: MemoryService = Depends(get_memory_service),
    billing: BillingService = Depends(get_billing_service),
) -> MemoryItemDTO:
    # A escrita pela borda também popula a chave lógica (titular_id) quando resolve.
    titular_id = _resolver_titular(billing, chat_id)
    return MemoryItemDTO.from_entity(svc.put(chat_id, body.chave, body.valor, titular_id))
