"""Billing & Account: titulares, contratos/UCs e faturas.
Alimenta: find_customer_by_phone, list_contracts, get_invoice_status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.application.services import (
    BillingService,
    InvoiceDocumentService,
    ProactiveService,
)
from src.interfaces.rest.dependencies import (
    get_billing_service,
    get_invoice_document_service,
    get_proactive_service,
)
from src.interfaces.rest.schemas import (
    ContractDTO,
    CustomerDTO,
    InvoiceDTO,
    InvoicePdfDTO,
    PersonaHintDTO,
    UnitDTO,
)

router = APIRouter(tags=["billing"])


@router.get("/personas", response_model=list[PersonaHintDTO])
def list_personas(
    svc: BillingService = Depends(get_billing_service),
) -> list[PersonaHintDTO]:
    """Personas cadastradas (atalhos da primeira tela do console). Telefone em
    claro — é o atalho de busca do operador (SPEC-012)."""
    return [PersonaHintDTO.from_entity(t) for t in svc.list_personas()]


@router.get("/customers", response_model=CustomerDTO)
def find_customer_by_phone(
    phone: str = Query(..., description="Telefone do remetente (E.164)"),
    svc: BillingService = Depends(get_billing_service),
) -> CustomerDTO:
    return CustomerDTO.from_entity(svc.find_customer_by_phone(phone))


@router.get("/customers/{titular_id}", response_model=CustomerDTO)
def get_customer(
    titular_id: uuid.UUID,
    svc: BillingService = Depends(get_billing_service),
) -> CustomerDTO:
    return CustomerDTO.from_entity(svc.get_customer(titular_id))


@router.get("/customers/{titular_id}/contracts", response_model=list[ContractDTO])
def list_contracts(
    titular_id: uuid.UUID,
    svc: BillingService = Depends(get_billing_service),
) -> list[ContractDTO]:
    return [ContractDTO.from_entity(c) for c in svc.list_contracts(titular_id)]


@router.get("/units/{uc_id}", response_model=UnitDTO)
def get_unit(
    uc_id: uuid.UUID,
    svc: BillingService = Depends(get_billing_service),
) -> UnitDTO:
    return UnitDTO.from_entity(svc.get_unidade(uc_id))


@router.get("/units/{uc_id}/invoices", response_model=list[InvoiceDTO])
def list_unit_invoices(
    uc_id: uuid.UUID,
    status: str | None = Query(None, description="paga | em_aberto | vencida"),
    limit: int = Query(12, ge=1, le=100),
    svc: BillingService = Depends(get_billing_service),
) -> list[InvoiceDTO]:
    return [InvoiceDTO.from_entity(f) for f in svc.list_invoices(uc_id, status, limit)]


@router.get("/invoices/{fatura_id}", response_model=InvoiceDTO)
def get_invoice_status(
    fatura_id: uuid.UUID,
    svc: BillingService = Depends(get_billing_service),
) -> InvoiceDTO:
    return InvoiceDTO.from_entity(svc.get_invoice(fatura_id))


class InvoiceStatusReq(BaseModel):
    status: str = Field(description="em_aberto | vencida")


@router.patch("/invoices/{fatura_id}/status", response_model=InvoiceDTO)
def update_invoice_status(
    fatura_id: uuid.UUID,
    req: InvoiceStatusReq,
    svc: BillingService = Depends(get_billing_service),
    proactive: ProactiveService = Depends(get_proactive_service),
) -> InvoiceDTO:
    """Operador ajusta o status da fatura (em_aberto/vencida). Reverter de 'paga'
    desfaz a baixa (SPEC-011). 'vencida' dispara o aviso proativo (best-effort);
    'em aberto' é silencioso."""
    fatura = svc.atualizar_status_fatura(fatura_id, req.status)
    if req.status == "vencida":
        titular = svc.get_titular_por_fatura(fatura_id)
        proactive.disparar_por_telefone(
            titular.telefone.value, "pagamento", "vencida",
            {"fatura_id": str(fatura_id), "mes": fatura.mes_referencia,
             "valor": fatura.valor.formatado()},
        )
    return InvoiceDTO.from_entity(fatura)


@router.get("/invoices/{fatura_id}/pdf", response_model=InvoicePdfDTO)
def generate_invoice_pdf(
    fatura_id: uuid.UUID,
    presigned: bool = Query(False, description="Devolve link pré-assinado com expiração"),
    expires: int = Query(3600, ge=60, le=604800, description="TTL do link pré-assinado (s)"),
    svc: InvoiceDocumentService = Depends(get_invoice_document_service),
) -> InvoicePdfDTO:
    """Render realista + persistência (MinIO). Não re-renderiza se já existe
    (ADR-0009); `presigned=true` regera só o link com expiração."""
    doc = svc.obter_ou_gerar(fatura_id, presign=presigned, expires=expires)
    return InvoicePdfDTO(
        url=doc.url, presigned=doc.presigned, expires_at=doc.expires_at,
        generated=doc.gerado_agora,
    )


@router.post("/invoices/{fatura_id}/send")
def send_invoice(
    fatura_id: uuid.UUID,
    expires: int = Query(3600, ge=60, le=604800),
    svc: InvoiceDocumentService = Depends(get_invoice_document_service),
) -> dict[str, object]:
    """Envia a 2ª via ao titular: PDF anexo no WhatsApp + link no texto (SPEC-017)."""
    return svc.enviar_2a_via(fatura_id, expires=expires)
