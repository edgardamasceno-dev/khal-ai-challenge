"""Testes do InvoiceDocumentService (SPEC-008): idempotência + presigned."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from src.application.services import InvoiceDocumentService
from src.domain.billing.documento import FaturaDetalhada
from src.domain.billing.entities import Fatura, Titular, UnidadeConsumidora
from src.domain.shared.errors import NotFoundError
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from tests.unit.fakes import (
    FakeFaturaRepository,
    FakeTitularRepository,
    FakeUnidadeRepository,
)

TIT_ID, UC_ID, FAT_ID = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class CountingRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def render(self, detalhe: FaturaDetalhada) -> bytes:
        self.calls += 1
        return b"%PDF-1.7 fake"


class MemStorage:
    def __init__(self) -> None:
        self.objs: dict[str, bytes] = {}

    def exists(self, key: str) -> bool:
        return key in self.objs

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objs[key] = data

    def public_url(self, key: str) -> str:
        return f"http://gateway/files/{key}"

    def presigned_url(self, key: str, expires_seconds: int) -> str:
        return f"http://minio/{key}?X-Expires={expires_seconds}&sig=abc"


def _service() -> tuple[InvoiceDocumentService, CountingRenderer, MemStorage]:
    titular = Titular(id=TIT_ID, nome="Edgar", cpf=CPF("52998224725"),
                      telefone=Telefone("5581993112159"), email=None, persona_key="edgar")
    uc = UnidadeConsumidora(id=UC_ID, numero_uc="767179274", titular_id=TIT_ID,
                            logradouro="Rua A", bairro="Jardim das Flores", cidade="Vale do Sol",
                            uf="SP", classe="residencial", subgrupo="B1", status="ativa")
    fatura = Fatura(id=FAT_ID, uc_id=UC_ID, mes_referencia="2026-05", consumo_kwh=247,
                    valor=Dinheiro(26869), bandeira="amarela", vencimento=dt.date(2026, 6, 10),
                    status="em_aberto", linha_digitavel="34191", pix_copia_cola="000201")
    renderer, storage = CountingRenderer(), MemStorage()
    svc = InvoiceDocumentService(
        faturas=FakeFaturaRepository([fatura]),
        unidades=FakeUnidadeRepository([uc]),
        titulares=FakeTitularRepository([titular]),
        renderer=renderer, storage=storage,
        clock=lambda: dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
    )
    return svc, renderer, storage


def test_primeira_vez_renderiza_e_armazena() -> None:
    svc, renderer, storage = _service()
    doc = svc.obter_ou_gerar(FAT_ID)
    assert renderer.calls == 1
    assert doc.gerado_agora is True
    assert doc.presigned is False
    assert doc.url == f"http://gateway/files/invoices/{FAT_ID}.pdf"
    assert f"invoices/{FAT_ID}.pdf" in storage.objs


def test_idempotente_nao_re_renderiza() -> None:
    svc, renderer, _ = _service()
    svc.obter_ou_gerar(FAT_ID)
    doc2 = svc.obter_ou_gerar(FAT_ID)
    assert renderer.calls == 1  # NÃO re-renderizou
    assert doc2.gerado_agora is False


def test_presigned_regenera_so_o_link() -> None:
    svc, renderer, _ = _service()
    svc.obter_ou_gerar(FAT_ID)  # gera o PDF
    doc = svc.obter_ou_gerar(FAT_ID, presign=True, expires=900)
    assert renderer.calls == 1  # PDF permanece, não re-renderiza
    assert doc.presigned is True
    assert "X-Expires=900" in doc.url
    assert doc.expires_at == dt.datetime(2026, 6, 1, 0, 15, tzinfo=dt.UTC)


def test_fatura_inexistente_404() -> None:
    svc, _, _ = _service()
    with pytest.raises(NotFoundError):
        svc.obter_ou_gerar(uuid.uuid4())
