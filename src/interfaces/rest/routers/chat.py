"""Aba Chat do operador (SPEC-018): transcript do canal + takeover/envio.

Proxy do Omni: a UI não fala com o Omni direto. `phone` é o telefone do cliente;
o adapter resolve o chat. Assumir/devolver reusa o agentPaused (SPEC-016).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.application.services import OperatorChatService, TicketingService
from src.interfaces.rest.dependencies import (
    get_operator_chat_service,
    get_ticketing_service,
)
from src.interfaces.rest.schemas import (
    ChatMessageDTO,
    ChatStatusDTO,
    ChatTranscriptDTO,
    SendMessageRequest,
)

router = APIRouter(tags=["chat"], prefix="/chats")


@router.get("/{phone}/messages", response_model=ChatTranscriptDTO)
def get_messages(
    phone: str,
    limit: int = Query(10, ge=1, le=50),
    cursor: str | None = Query(None),
    svc: OperatorChatService = Depends(get_operator_chat_service),
) -> ChatTranscriptDTO:
    itens, prox, tem_mais = svc.transcript(phone, limit=limit, cursor=cursor)
    return ChatTranscriptDTO(
        mensagens=[ChatMessageDTO.from_entity(m) for m in itens],
        cursor=prox,
        tem_mais=tem_mais,
    )


@router.get("/{phone}/status", response_model=ChatStatusDTO)
def get_status(
    phone: str,
    svc: OperatorChatService = Depends(get_operator_chat_service),
) -> ChatStatusDTO:
    return ChatStatusDTO(pausado=bool(svc.status(phone)["pausado"]))


@router.post("/{phone}/takeover", response_model=ChatStatusDTO)
def takeover(
    phone: str,
    ticketing: TicketingService = Depends(get_ticketing_service),
) -> ChatStatusDTO:
    """Operador assume o controle: pausa a IA **e registra o handoff** na fila, para
    a aba Chamados e a aba Chat ficarem consistentes (SPEC-018)."""
    ticketing.request_handoff(
        chamado_id=None, motivo="Operador assumiu pelo chat", remetente=phone
    )
    return ChatStatusDTO(pausado=True)


@router.post("/{phone}/release", response_model=ChatStatusDTO)
def release(
    phone: str,
    svc: OperatorChatService = Depends(get_operator_chat_service),
    ticketing: TicketingService = Depends(get_ticketing_service),
) -> ChatStatusDTO:
    """Operador devolve ao agente: retoma a IA **e resolve os handoffs pendentes**
    do cliente, para a fila de Chamados não ficar com registros órfãos (SPEC-018)."""
    svc.release(phone)
    ticketing.resolver_handoffs_do_remetente(phone)
    return ChatStatusDTO(pausado=False)


@router.post("/{phone}/send")
def send_message(
    phone: str,
    body: SendMessageRequest,
    svc: OperatorChatService = Depends(get_operator_chat_service),
) -> dict[str, object]:
    """Operador envia uma mensagem ao cliente (texto)."""
    return svc.send(phone, body.texto)
