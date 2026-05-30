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
    MemoryService,
    OutageService,
    TicketingService,
)
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.knowledge.entities import ResultadoKB
from src.domain.outage.entities import Interrupcao
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from src.interfaces.rest.app import create_app
from src.interfaces.rest.dependencies import (
    get_billing_service,
    get_knowledge_retrieval,
    get_memory_service,
    get_outage_service,
    get_session,
    get_ticketing_service,
)
from tests.unit.fakes import (
    FakeChamadoRepository,
    FakeFaturaRepository,
    FakeHandoffRepository,
    FakeInterrupcaoRepository,
    FakeKnowledgeRetrieval,
    FakeMemoriaRepository,
    FakeTitularRepository,
    FakeUnidadeRepository,
    FakeUnitOfWork,
)

ANA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
UC_ID = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
FAT_ID = uuid.UUID("ffff0001-0000-0000-0000-000000000001")


class _FakeSession:
    def execute(self, *args: object, **kwargs: object) -> None:
        return None


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

    billing = BillingService(titulares, FakeUnidadeRepository([uc]), FakeFaturaRepository([fatura]))
    outage_svc = OutageService(FakeInterrupcaoRepository([outage]))
    ticketing = TicketingService(chamados, handoffs, titulares, uow)
    memory = MemoryService(memorias, uow)
    knowledge = FakeKnowledgeRetrieval(
        [ResultadoKB("titularidade", "Transferencia de titularidade", "Para transferir...", 9)]
    )

    app = create_app()
    app.dependency_overrides[get_billing_service] = lambda: billing
    app.dependency_overrides[get_outage_service] = lambda: outage_svc
    app.dependency_overrides[get_ticketing_service] = lambda: ticketing
    app.dependency_overrides[get_memory_service] = lambda: memory
    app.dependency_overrides[get_knowledge_retrieval] = lambda: knowledge
    app.dependency_overrides[get_session] = lambda: _FakeSession()

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, chamados=chamados, handoffs=handoffs)
