"""Ticketing & Handoff. Alimenta: create_ticket, get_ticket_status,
request_human_handoff.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from src.application.services import TicketingService
from src.interfaces.rest.dependencies import get_ticketing_service
from src.interfaces.rest.schemas import (
    CreateTicketRequest,
    CreateTicketResponse,
    HandoffDTO,
    HandoffRequest,
    ResumeHandoffRequest,
    TicketDTO,
)

router = APIRouter(tags=["ticketing"])


@router.post("/tickets", response_model=CreateTicketResponse)
def create_ticket(
    body: CreateTicketRequest,
    response: Response,
    svc: TicketingService = Depends(get_ticketing_service),
) -> CreateTicketResponse:
    chamado, criado = svc.open_ticket(
        titular_id=body.titular_id,
        uc_id=body.uc_id,
        tipo=body.tipo.value,
        descricao=body.descricao,
        idempotency_key=body.idempotency_key,
    )
    response.status_code = status.HTTP_201_CREATED if criado else status.HTTP_200_OK
    return CreateTicketResponse(criado_agora=criado, ticket=TicketDTO.from_entity(chamado))


@router.get("/tickets/{protocolo}", response_model=TicketDTO)
def get_ticket_status(
    protocolo: str,
    svc: TicketingService = Depends(get_ticketing_service),
) -> TicketDTO:
    return TicketDTO.from_entity(svc.get_ticket_status(protocolo))


@router.get("/customers/{titular_id}/tickets", response_model=list[TicketDTO])
def list_customer_tickets(
    titular_id: uuid.UUID,
    svc: TicketingService = Depends(get_ticketing_service),
) -> list[TicketDTO]:
    return [TicketDTO.from_entity(c) for c in svc.list_customer_tickets(titular_id)]


@router.post("/handoffs", response_model=HandoffDTO, status_code=status.HTTP_201_CREATED)
def request_human_handoff(
    body: HandoffRequest,
    svc: TicketingService = Depends(get_ticketing_service),
) -> HandoffDTO:
    return HandoffDTO.from_entity(
        svc.request_handoff(
            chamado_id=body.chamado_id, motivo=body.motivo, remetente=body.remetente
        )
    )


@router.get("/handoffs", response_model=list[HandoffDTO])
def list_handoffs(
    svc: TicketingService = Depends(get_ticketing_service),
) -> list[HandoffDTO]:
    """Fila de handoffs pendentes (atendimento humano em aberto)."""
    return [HandoffDTO.from_entity(h) for h in svc.list_handoffs()]


@router.post("/handoffs/{handoff_id}/resume", response_model=HandoffDTO)
def resume_handoff(
    handoff_id: uuid.UUID,
    body: ResumeHandoffRequest,
    svc: TicketingService = Depends(get_ticketing_service),
) -> HandoffDTO:
    """Operador devolve o atendimento à IA (retoma o agente no Omni)."""
    return HandoffDTO.from_entity(svc.resume_handoff(handoff_id, body.operador))
