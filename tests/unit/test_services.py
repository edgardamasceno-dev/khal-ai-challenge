from __future__ import annotations

import datetime as dt
import uuid

import pytest

from src.application.services import (
    BillingService,
    MemoryService,
    OutageService,
    TicketingService,
)
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.outage.entities import Interrupcao
from src.domain.shared.errors import InvariantError, NotFoundError
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from tests.unit.fakes import (
    FakeChamadoRepository,
    FakeFaturaRepository,
    FakeHandoffRepository,
    FakeInterrupcaoRepository,
    FakeMemoriaRepository,
    FakeTitularRepository,
    FakeUnidadeRepository,
    FakeUnitOfWork,
)

ANA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
UC_ID = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
FAT_ID = uuid.UUID("ffff0001-0000-0000-0000-000000000001")


def _ana() -> Titular:
    return Titular(
        id=ANA_ID,
        nome="Ana Souza",
        cpf=CPF("52998224725"),
        telefone=Telefone("555199990001"),
        email=None,
        persona_key="ana.souza",
    )


def _uc() -> UnidadeConsumidora:
    return UnidadeConsumidora(
        id=UC_ID,
        numero_uc="100000001",
        titular_id=ANA_ID,
        logradouro=None,
        bairro="Jardim das Flores",
        cidade="Vale do Sol",
        uf="SP",
        classe="residencial",
        subgrupo="B1",
        status="ativa",
    )


def _fatura() -> Fatura:
    return Fatura(
        id=FAT_ID,
        uc_id=UC_ID,
        mes_referencia="2026-05",
        consumo_kwh=200,
        valor=Dinheiro(19000),
        bandeira="amarela",
        vencimento=dt.date(2026, 6, 10),
        status="em_aberto",
        linha_digitavel=None,
        pix_copia_cola=None,
    )


def _billing() -> BillingService:
    contrato = Contrato(
        id=uuid.uuid4(),
        modalidade="convencional",
        data_inicio=dt.date(2019, 3, 10),
        status="ativo",
        unidade=_uc(),
    )
    return BillingService(
        FakeTitularRepository([_ana()], {ANA_ID: [contrato]}),
        FakeUnidadeRepository([_uc()]),
        FakeFaturaRepository([_fatura()]),
    )


class TestBillingService:
    def test_find_by_phone_conhecido(self) -> None:
        assert _billing().find_customer_by_phone("555199990001").persona_key == "ana.souza"

    def test_find_by_phone_desconhecido_404(self) -> None:
        with pytest.raises(NotFoundError):
            _billing().find_customer_by_phone("551999999999")

    def test_find_by_phone_invalido_422(self) -> None:
        with pytest.raises(InvariantError):
            _billing().find_customer_by_phone("123")

    def test_list_contracts(self) -> None:
        contratos = _billing().list_contracts(ANA_ID)
        assert len(contratos) == 1
        assert contratos[0].unidade.bairro == "Jardim das Flores"

    def test_list_contracts_titular_inexistente(self) -> None:
        with pytest.raises(NotFoundError):
            _billing().list_contracts(uuid.uuid4())

    def test_get_invoice(self) -> None:
        f = _billing().get_invoice(FAT_ID)
        assert f.status == "em_aberto" and f.valor.formatado() == "R$ 190.00"

    def test_get_invoice_inexistente(self) -> None:
        with pytest.raises(NotFoundError):
            _billing().get_invoice(uuid.uuid4())

    def test_list_invoices_filtra_status(self) -> None:
        assert len(_billing().list_invoices(UC_ID, "em_aberto", 12)) == 1
        assert _billing().list_invoices(UC_ID, "paga", 12) == []


class TestOutageService:
    def _svc(self) -> OutageService:
        outage = Interrupcao(
            id=uuid.uuid4(),
            bairro="Jardim das Flores",
            cidade="Vale do Sol",
            uf="SP",
            tipo="nao_programada",
            causa="Falha de rede",
            inicio=dt.datetime.now(dt.UTC),
            previsao_retorno=None,
            status="ativa",
        )
        return OutageService(FakeInterrupcaoRepository([outage]))

    def test_encontra_outage_ativa(self) -> None:
        out = self._svc().find_active_by_region("Jardim das Flores")
        assert out is not None and out.tipo == "nao_programada"

    def test_sem_outage(self) -> None:
        assert self._svc().find_active_by_region("Centro") is None


class TestTicketingService:
    def _svc(self) -> tuple[TicketingService, FakeUnitOfWork, FakeChamadoRepository]:
        uow = FakeUnitOfWork()
        chamados = FakeChamadoRepository()
        svc = TicketingService(
            chamados,
            FakeHandoffRepository(),
            FakeTitularRepository([_ana()]),
            uow,
        )
        return svc, uow, chamados

    def test_open_ticket_cria(self) -> None:
        svc, uow, _ = self._svc()
        chamado, criado = svc.open_ticket(
            titular_id=ANA_ID, uc_id=UC_ID, tipo="falta_energia",
            descricao="sem luz", idempotency_key="k1",
        )
        assert criado is True
        assert chamado.protocolo.startswith("LDV") and chamado.sla_horas == 48
        assert uow.commits == 1

    def test_open_ticket_idempotente(self) -> None:
        svc, _, _ = self._svc()
        a, _ = svc.open_ticket(
            titular_id=ANA_ID, uc_id=UC_ID, tipo="falta_energia",
            descricao="x", idempotency_key="k1",
        )
        b, criado = svc.open_ticket(
            titular_id=ANA_ID, uc_id=UC_ID, tipo="falta_energia",
            descricao="x", idempotency_key="k1",
        )
        assert criado is False and b.protocolo == a.protocolo

    def test_open_ticket_titular_inexistente(self) -> None:
        svc, _, _ = self._svc()
        with pytest.raises(NotFoundError):
            svc.open_ticket(
                titular_id=uuid.uuid4(), uc_id=None, tipo="falta_energia",
                descricao=None, idempotency_key="k2",
            )

    def test_open_ticket_tipo_invalido(self) -> None:
        svc, _, _ = self._svc()
        with pytest.raises(InvariantError):
            svc.open_ticket(
                titular_id=ANA_ID, uc_id=None, tipo="xpto",
                descricao=None, idempotency_key="k3",
            )

    def test_get_ticket_status(self) -> None:
        svc, _, _ = self._svc()
        c, _ = svc.open_ticket(
            titular_id=ANA_ID, uc_id=None, tipo="religacao",
            descricao=None, idempotency_key="k4",
        )
        assert svc.get_ticket_status(c.protocolo).protocolo == c.protocolo

    def test_get_ticket_status_inexistente(self) -> None:
        svc, _, _ = self._svc()
        with pytest.raises(NotFoundError):
            svc.get_ticket_status("LDV20000101ZZZZ")

    def test_request_handoff(self) -> None:
        svc, uow, _ = self._svc()
        ho = svc.request_handoff(chamado_id=None, motivo="fora de escopo")
        assert ho.status == "pendente" and uow.commits == 1


class TestMemoryService:
    def test_put_e_get(self) -> None:
        svc = MemoryService(FakeMemoriaRepository(), FakeUnitOfWork())
        svc.put("chat-1", "ultimo_protocolo", {"protocolo": "LDV20260530AAAA"})
        itens = svc.get("chat-1")
        assert len(itens) == 1 and itens[0].chave == "ultimo_protocolo"

    def test_upsert_nao_duplica(self) -> None:
        svc = MemoryService(FakeMemoriaRepository(), FakeUnitOfWork())
        svc.put("chat-1", "k", {"v": 1})
        svc.put("chat-1", "k", {"v": 2})
        itens = svc.get("chat-1")
        assert len(itens) == 1 and itens[0].valor == {"v": 2}
