"""Fixtures da camada API: TestClient com servicos reais ligados a
repositorios fake (sem banco), injetados via dependency_overrides.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.application.services import (
    BillingService,
    HealthService,
    InvoiceDocumentService,
    MemoryService,
    OperatorChatService,
    OutageService,
    ProactiveService,
    TicketingService,
)
from src.domain.billing.documento import FaturaDetalhada
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.conversation.entities import MensagemChat
from src.domain.knowledge.entities import ResultadoKB
from src.domain.outage.entities import Interrupcao
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from src.interfaces.rest.app import create_app
from src.interfaces.rest.dependencies import (
    get_billing_service,
    get_health_service,
    get_invoice_document_service,
    get_knowledge_retrieval,
    get_memory_service,
    get_operator_chat_service,
    get_outage_service,
    get_proactive_service,
    get_session,
    get_ticketing_service,
)
from tests.unit.fakes import (
    FakeChamadoRepository,
    FakeChatTranscript,
    FakeFaturaRepository,
    FakeHandoffRepository,
    FakeInterrupcaoRepository,
    FakeKnowledgeRetrieval,
    FakeMemoriaRepository,
    FakeOmniSender,
    FakeTitularRepository,
    FakeUnidadeRepository,
    FakeUnitOfWork,
)

ANA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
UC_ID = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
FAT_ID = uuid.UUID("ffff0001-0000-0000-0000-000000000001")


class _FakeRenderer:
    def render(self, detalhe: FaturaDetalhada) -> bytes:
        return b"%PDF-1.7 fake"


class _FakeBus:
    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, subject: str, payload: dict) -> None:  # type: ignore[type-arg]
        self.published.append(subject)


class _FakeSender:
    def send_text(self, chat_id: str, texto: str) -> bool:
        return True

    def send_document(
        self, chat_id: str, conteudo: bytes, filename: str, caption: str = ""
    ) -> bool:
        return True


class _MemStorage:
    def __init__(self) -> None:
        self._objs: dict[str, bytes] = {}

    def exists(self, key: str) -> bool:
        return key in self._objs

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objs[key] = data

    def public_url(self, key: str) -> str:
        return f"http://localhost/files/{key}"

    def presigned_url(self, key: str, expires_seconds: int) -> str:
        return f"http://minio/{key}?X-Expires={expires_seconds}"


class _FakeSession:
    def execute(self, *args: object, **kwargs: object) -> None:
        return None


class _FakeChannelHealth:
    def whatsapp(self) -> str:
        return "ok"

    def agente(self) -> str:
        return "ok"


class _FakeChannelControl:
    def __init__(self) -> None:
        self.pausados: list[str] = []
        self.retomados: list[str] = []
        self.pausado = False

    def pausar_agente(self, remetente: str) -> bool:
        self.pausados.append(remetente)
        self.pausado = True
        return True

    def retomar_agente(self, remetente: str) -> bool:
        self.retomados.append(remetente)
        self.pausado = False
        return True

    def esta_pausado(self, remetente: str) -> bool:
        return self.pausado


@pytest.fixture
def ctx() -> Iterator[SimpleNamespace]:
    ana = Titular(
        id=ANA_ID, nome="Ana Souza", cpf=CPF("52998224725"),
        telefone=Telefone("555199990001"), email=None, persona_key="ana.souza",
    )
    uc = UnidadeConsumidora(
        id=UC_ID, numero_uc="100000001", titular_id=ANA_ID, logradouro=None,
        bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
        classe="residencial", subgrupo="B1", status="ativa",
    )
    contrato = Contrato(
        id=uuid.uuid4(), modalidade="convencional", data_inicio=dt.date(2019, 3, 10),
        status="ativo", unidade=uc,
    )
    fatura = Fatura(
        id=FAT_ID, uc_id=UC_ID, mes_referencia="2026-05", consumo_kwh=200,
        valor=Dinheiro(19000), bandeira="amarela", vencimento=dt.date(2026, 6, 10),
        status="em_aberto", linha_digitavel=None, pix_copia_cola=None,
    )
    outage = Interrupcao(
        id=uuid.uuid4(), bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
        tipo="nao_programada", causa="Falha de rede", inicio=dt.datetime.now(dt.UTC),
        previsao_retorno=None, status="ativa",
    )

    titulares = FakeTitularRepository([ana], {ANA_ID: [contrato]})
    chamados = FakeChamadoRepository()
    handoffs = FakeHandoffRepository()
    memorias = FakeMemoriaRepository()
    uow = FakeUnitOfWork()

    faturas_repo = FakeFaturaRepository([fatura])
    billing = BillingService(titulares, FakeUnidadeRepository([uc]), faturas_repo, uow)
    invoice_doc = InvoiceDocumentService(
        FakeFaturaRepository([fatura]), FakeUnidadeRepository([uc]), titulares,
        _FakeRenderer(), _MemStorage(), sender=_FakeSender(),
        clock=lambda: dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
    )
    bus = _FakeBus()
    proactive = ProactiveService(
        bus, _FakeSender(), memorias, titulares,
        faturas_repo, FakeInterrupcaoRepository([outage]), uow,
        clock=lambda: dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
    )
    outage_svc = OutageService(FakeInterrupcaoRepository([outage]))
    control = _FakeChannelControl()
    # SPEC-020: injeta o sender p/ assertir notificacao (resolve/notificar) na API.
    ticket_sender = FakeOmniSender()
    ticketing = TicketingService(
        chamados, handoffs, titulares, uow, control=control, sender=ticket_sender
    )
    chat_msgs = [
        MensagemChat(id="m1", texto="Oi, preciso da 2ª via", do_cliente=True,
                     em=dt.datetime(2026, 5, 31, 3, tzinfo=dt.UTC)),
        MensagemChat(id="m2", texto="Claro! Enviei o PDF.", do_cliente=False,
                     em=dt.datetime(2026, 5, 31, 3, 1, tzinfo=dt.UTC)),
    ]
    op_chat = OperatorChatService(
        FakeChatTranscript(chat_msgs), control, _FakeSender()
    )
    memory = MemoryService(memorias, uow)
    knowledge = FakeKnowledgeRetrieval(
        [ResultadoKB("titularidade", "Transferencia de titularidade", "Para transferir...", 9)]
    )

    app = create_app()
    app.dependency_overrides[get_billing_service] = lambda: billing
    app.dependency_overrides[get_invoice_document_service] = lambda: invoice_doc
    app.dependency_overrides[get_proactive_service] = lambda: proactive
    app.dependency_overrides[get_outage_service] = lambda: outage_svc
    app.dependency_overrides[get_ticketing_service] = lambda: ticketing
    app.dependency_overrides[get_memory_service] = lambda: memory
    app.dependency_overrides[get_knowledge_retrieval] = lambda: knowledge
    app.dependency_overrides[get_session] = lambda: _FakeSession()
    app.dependency_overrides[get_health_service] = lambda: HealthService(_FakeChannelHealth())
    app.dependency_overrides[get_operator_chat_service] = lambda: op_chat

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, chamados=chamados, handoffs=handoffs, bus=bus,
            control=control, fatura_id=FAT_ID, ticket_sender=ticket_sender,
        )
