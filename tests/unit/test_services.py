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
    FakeChannelControl,
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
        FakeUnitOfWork(),
    )


class TestBillingService:
    def test_find_by_phone_conhecido(self) -> None:
        assert _billing().find_customer_by_phone("555199990001").persona_key == "ana.souza"

    def test_find_by_phone_desconhecido_404(self) -> None:
        with pytest.raises(NotFoundError):
            _billing().find_customer_by_phone("551999999999")

    def test_find_by_phone_nao_identificado_404(self) -> None:
        # SPEC-015: identidade flexível (aceita LID); o que não resolve é 404, não 422.
        with pytest.raises(NotFoundError):
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

    def test_atualizar_status_fatura(self) -> None:
        svc = _billing()
        f = svc.atualizar_status_fatura(FAT_ID, "vencida")
        assert f.status == "vencida"
        assert svc.get_invoice(FAT_ID).status == "vencida"

    def test_atualizar_status_invalido(self) -> None:
        with pytest.raises(InvariantError):
            _billing().atualizar_status_fatura(FAT_ID, "paga")

    def test_atualizar_status_fatura_inexistente(self) -> None:
        with pytest.raises(NotFoundError):
            _billing().atualizar_status_fatura(uuid.uuid4(), "vencida")

    def test_get_titular_por_fatura(self) -> None:
        assert _billing().get_titular_por_fatura(FAT_ID).persona_key == "ana.souza"

    def test_list_personas(self) -> None:
        personas = _billing().list_personas()
        assert [p.persona_key for p in personas] == ["ana.souza"]
        assert personas[0].telefone.value == "555199990001"


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

    def _svc_handoff(
        self,
    ) -> tuple[TicketingService, FakeHandoffRepository, FakeChannelControl]:
        handoffs = FakeHandoffRepository()
        control = FakeChannelControl()
        svc = TicketingService(
            FakeChamadoRepository(), handoffs, FakeTitularRepository([_ana()]),
            FakeUnitOfWork(), control=control,
        )
        return svc, handoffs, control

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

    def test_request_handoff_pausa_a_ia(self) -> None:
        # SPEC-016: com remetente + canal, registra e pausa o agente no Omni.
        svc, _, control = self._svc_handoff()
        ho = svc.request_handoff(
            chamado_id=None, motivo="quer atendente", remetente="87866608713902@lid"
        )
        # remetente é normalizado (sem @lid) para casar com a aba Chat (SPEC-018)
        assert ho.status == "pendente" and ho.remetente == "87866608713902"
        assert control.pausados == ["87866608713902@lid"]

    def test_request_handoff_sem_remetente_nao_pausa(self) -> None:
        svc, _, control = self._svc_handoff()
        svc.request_handoff(chamado_id=None, motivo="x", remetente=None)
        assert control.pausados == []

    def test_list_e_resume_handoff(self) -> None:
        svc, _, control = self._svc_handoff()
        ho = svc.request_handoff(chamado_id=None, motivo="x", remetente="5581993112159")
        assert [h.id for h in svc.list_handoffs()] == [ho.id]  # pendente na fila
        resolvido = svc.resume_handoff(ho.id, operador="ana.op")
        assert resolvido.status == "resolvido" and resolvido.operador == "ana.op"
        assert control.retomados == ["5581993112159"]
        assert svc.list_handoffs() == []  # saiu da fila

    def test_resume_handoff_inexistente(self) -> None:
        svc, _, _ = self._svc_handoff()
        with pytest.raises(NotFoundError):
            svc.resume_handoff(uuid.uuid4())

    def test_resolver_handoffs_do_remetente_casa_por_telefone(self) -> None:
        # SPEC-018: devolver pela aba Chat resolve o handoff pendente (casa pelo 9º dígito).
        svc, handoffs, _ = self._svc_handoff()
        svc.request_handoff(chamado_id=None, motivo="x", remetente="558193112159")  # sem 9
        assert len(svc.list_handoffs()) == 1
        n = svc.resolver_handoffs_do_remetente("5581993112159")  # com 9
        assert n == 1 and svc.list_handoffs() == []

    def test_resolver_handoffs_ignora_outro_cliente(self) -> None:
        svc, _, _ = self._svc_handoff()
        svc.request_handoff(chamado_id=None, motivo="x", remetente="558193112159")
        assert svc.resolver_handoffs_do_remetente("550000000000") == 0
        assert len(svc.list_handoffs()) == 1


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
