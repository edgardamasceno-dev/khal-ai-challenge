"""Billing & Account: titulares, contratos/UCs e faturas.
Alimenta: find_customer_by_phone, list_contracts, get_invoice_status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.application.services import BillingService
from src.interfaces.rest.dependencies import get_billing_service
from src.interfaces.rest.schemas import ContractDTO, CustomerDTO, InvoiceDTO, UnitDTO

router = APIRouter(tags=["billing"])


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


@router.get("/invoices/{fatura_id}/pdf")
def generate_invoice_pdf(fatura_id: uuid.UUID) -> JSONResponse:
    # Reservado (ADR-0003): render WeasyPrint + envio via Omni sao SPEC propria.
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "code": "NotImplemented",
                "message": "Geracao/envio de PDF entra em SPEC futura (ADR-0003).",
            }
        },
    )
