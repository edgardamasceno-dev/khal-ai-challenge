"""Teste do endpoint GET /api/invoices/{id}/pdf (SPEC-008)."""

from __future__ import annotations

from types import SimpleNamespace

FAT = "ffff0001-0000-0000-0000-000000000001"


def test_pdf_url_estavel_via_gateway(ctx: SimpleNamespace) -> None:
    r = ctx.client.get(f"/api/invoices/{FAT}/pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == f"http://localhost/files/invoices/{FAT}.pdf"
    assert body["presigned"] is False
    assert body["generated"] is True  # 1a vez renderizou


def test_pdf_idempotente_segunda_vez_nao_gera(ctx: SimpleNamespace) -> None:
    ctx.client.get(f"/api/invoices/{FAT}/pdf")
    r = ctx.client.get(f"/api/invoices/{FAT}/pdf")
    assert r.json()["generated"] is False  # veio do storage


def test_pdf_presigned_com_expiracao(ctx: SimpleNamespace) -> None:
    r = ctx.client.get(f"/api/invoices/{FAT}/pdf?presigned=true&expires=900")
    assert r.status_code == 200
    body = r.json()
    assert body["presigned"] is True
    assert "X-Expires=900" in body["url"]
    assert body["expires_at"] is not None


def test_pdf_fatura_inexistente_404(ctx: SimpleNamespace) -> None:
    r = ctx.client.get("/api/invoices/00000000-0000-0000-0000-000000000000/pdf")
    assert r.status_code == 404
