"""Conversation: memoria curta por chatId (RF-11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.application.services import MemoryService
from src.interfaces.rest.dependencies import get_memory_service
from src.interfaces.rest.schemas import MemoryItemDTO, MemoryPutRequest

router = APIRouter(tags=["conversation"])


@router.get("/conversations/{chat_id}/memory", response_model=list[MemoryItemDTO])
def get_memory(
    chat_id: str,
    svc: MemoryService = Depends(get_memory_service),
) -> list[MemoryItemDTO]:
    return [MemoryItemDTO.from_entity(m) for m in svc.get(chat_id)]


@router.put("/conversations/{chat_id}/memory", response_model=MemoryItemDTO)
def put_memory(
    chat_id: str,
    body: MemoryPutRequest,
    svc: MemoryService = Depends(get_memory_service),
) -> MemoryItemDTO:
    return MemoryItemDTO.from_entity(svc.put(chat_id, body.chave, body.valor))
