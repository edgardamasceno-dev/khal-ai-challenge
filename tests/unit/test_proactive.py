"""Testes do ProactiveService (SPEC-009): disparo, processamento, candidatos."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from src.application.services import ProactiveService
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.notifications.entities import EventoCX
from src.domain.outage.entities import Interrupcao
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from tests.unit.fakes import (
    FakeFaturaRepository,
    FakeInterrupcaoRepository,
    FakeMemoriaRepository,
    FakeTitularRepository,
    FakeUnitOfWork,
)

TID, UCID, FID = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


class FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self.published.append((subject, payload))


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_text(self, chat_id: str, texto: str) -> bool:
        self.sent.append((chat_id, texto))
        return True


def _svc(
    com_outage: bool = True,
) -> tuple[ProactiveService, FakeBus, FakeSender, FakeMemoriaRepository]:
    t = Titular(id=TID, nome="Edgar Damasceno", cpf=CPF("52998224725"),
                telefone=Telefone("5581993112159"), email=None, persona_key="edgar")
    uc = UnidadeConsumidora(id=UCID, numero_uc="767179274", titular_id=TID, logradouro="R",
                            bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
                            classe="residencial", subgrupo="B1", status="ativa")
    contrato = Contrato(id=uuid.uuid4(), modalidade="convencional",
                        data_inicio=dt.date(2019, 3, 10), status="ativo", unidade=uc)
    fatura = Fatura(id=FID, uc_id=UCID, mes_referencia="2026-05", consumo_kwh=247,
                    valor=Dinheiro(26869), bandeira="amarela", vencimento=dt.date(2026, 6, 10),
                    status="em_aberto", linha_digitavel=None, pix_copia_cola=None)
    inter = (
        [Interrupcao(id=uuid.uuid4(), bairro="Jardim das Flores", cidade="Vale do Sol",
                     uf="SP", tipo="nao_programada", causa="Falha",
                     inicio=dt.datetime.now(dt.UTC), previsao_retorno=None, status="ativa")]
        if com_outage else []
    )
    bus, sender, mem = FakeBus(), FakeSender(), FakeMemoriaRepository()
    svc = ProactiveService(
        bus, sender, mem,
        FakeTitularRepository([t], {TID: [contrato]}),
        FakeFaturaRepository([fatura]),
        FakeInterrupcaoRepository(inter),
        FakeUnitOfWork(),
        clock=lambda: dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
    )
    return svc, bus, sender, mem


def _ev() -> EventoCX:
    return EventoCX(tipo="pagamento", subtipo="confirmado", telefone="5581993112159",
                    nome="Edgar Damasceno", idempotency_key="pay-1",
                    dados={"mes": "05/2026", "valor": "R$ 268,69"})


def test_disparar_publica_no_bus_e_devolve_preview() -> None:
    svc, bus, _, _ = _svc()
    r = svc.disparar(_ev())
    assert bus.published[0][0] == "utilitycx.pagamento.confirmado"
    assert "Edgar" in str(r["preview"])
    assert r["publicado"] is True


def test_processar_envia_e_grava_memoria() -> None:
    svc, _, sender, mem = _svc()
    r = svc.processar(_ev())
    assert sender.sent and "R$ 268,69" in sender.sent[0][1]
    assert r["enviado"] is True
    memos = mem.list_for_chat("5581993112159")
    assert memos[0].chave == "proativo.pagamento.confirmado"


def test_candidatos_lista_pagamento_e_outage() -> None:
    svc, _, _, _ = _svc(com_outage=True)
    c = svc.candidatos("5581993112159")
    assert c["encontrado"] is True
    assert c["pagamentos"] and c["pagamentos"][0]["status"] == "em_aberto"
    assert c["outages"] and c["outages"][0]["bairro"] == "Jardim das Flores"


def test_candidatos_sem_outage() -> None:
    svc, _, _, _ = _svc(com_outage=False)
    assert svc.candidatos("5581993112159")["outages"] == []


def test_candidatos_telefone_desconhecido() -> None:
    svc, _, _, _ = _svc()
    assert svc.candidatos("550000000000")["encontrado"] is False
