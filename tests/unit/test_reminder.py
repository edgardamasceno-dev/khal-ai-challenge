"""Lembrete proativo de vencimento D-3/D-0 (R-16 / SPEC-026).

DETERMINÍSTICO, sem LLM: dado um `hoje`, o ProactiveReminderService varre as faturas
em aberto/vencida e publica `utilitycx.pagamento.lembrete` só para os vencimentos em
D-3 e D-0, de forma idempotente por (fatura_id, dia).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from src.application.services import ProactiveReminderService
from src.domain.billing.entities import Contrato, Fatura, Titular, UnidadeConsumidora
from src.domain.notifications.entities import EVENTOS_VALIDOS, EventoCX
from src.domain.notifications.templates import render_notificacao
from src.domain.shared.value_objects import CPF, Dinheiro, Telefone
from tests.unit.fakes import (
    FakeFaturaRepository,
    FakeMemoriaRepository,
    FakeTitularRepository,
    FakeUnitOfWork,
)

TID = uuid.uuid4()
UCID = uuid.uuid4()
TELEFONE = "5581993112159"
HOJE = dt.date(2026, 6, 1)


class FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        self.published.append((subject, payload))


def _titular() -> Titular:
    return Titular(
        id=TID, nome="Edgar Damasceno", cpf=CPF("52998224725"),
        telefone=Telefone(TELEFONE), email=None, persona_key="edgar",
    )


def _uc() -> UnidadeConsumidora:
    return UnidadeConsumidora(
        id=UCID, numero_uc="767179274", titular_id=TID, logradouro="R",
        bairro="Jardim das Flores", cidade="Vale do Sol", uf="SP",
        classe="residencial", subgrupo="B1", status="ativa",
    )


def _fatura(venc: dt.date, status: str = "em_aberto", fid: uuid.UUID | None = None) -> Fatura:
    return Fatura(
        id=fid or uuid.uuid4(), uc_id=UCID, mes_referencia="2026-06", consumo_kwh=247,
        valor=Dinheiro(26869), bandeira="amarela", vencimento=venc,
        status=status, linha_digitavel=None, pix_copia_cola=None,
    )


def _svc(
    faturas: list[Fatura],
) -> tuple[ProactiveReminderService, FakeBus, FakeMemoriaRepository]:
    contrato = Contrato(
        id=uuid.uuid4(), modalidade="convencional", data_inicio=dt.date(2019, 3, 10),
        status="ativo", unidade=_uc(),
    )
    bus, mem = FakeBus(), FakeMemoriaRepository()
    svc = ProactiveReminderService(
        bus, mem,
        FakeTitularRepository([_titular()], {TID: [contrato]}),
        FakeFaturaRepository(faturas),
        FakeUnitOfWork(),
        clock=lambda: dt.datetime(2026, 6, 1, 12, tzinfo=dt.UTC),
    )
    return svc, bus, mem


def test_evento_lembrete_e_valido() -> None:
    assert ("pagamento", "lembrete") in EVENTOS_VALIDOS


def test_d3_dispara_lembrete() -> None:
    # vencimento em 04/06 = D-3 de 01/06.
    svc, bus, _ = _svc([_fatura(HOJE + dt.timedelta(days=3))])
    r = svc.varrer(HOJE)
    assert r["total"] == 1
    subject, payload = bus.published[0]
    assert subject == "utilitycx.pagamento.lembrete"
    assert payload["dados"]["dias_para_vencer"] == 3


def test_d0_dispara_lembrete() -> None:
    svc, bus, _ = _svc([_fatura(HOJE)])
    r = svc.varrer(HOJE)
    assert r["total"] == 1
    assert bus.published[0][1]["dados"]["dias_para_vencer"] == 0


def test_d1_e_d5_nao_disparam() -> None:
    # Só D-3 e D-0 são elegíveis (thresholds fixos, determinísticos).
    svc, bus, _ = _svc([
        _fatura(HOJE + dt.timedelta(days=1)),
        _fatura(HOJE + dt.timedelta(days=5)),
    ])
    assert svc.varrer(HOJE)["total"] == 0
    assert bus.published == []


def test_fatura_paga_nao_dispara() -> None:
    svc, bus, _ = _svc([_fatura(HOJE, status="paga")])
    assert svc.varrer(HOJE)["total"] == 0
    assert bus.published == []


def test_fatura_vencida_em_d0_dispara() -> None:
    # status 'vencida' também é lembrável (cobrança).
    svc, bus, _ = _svc([_fatura(HOJE, status="vencida")])
    assert svc.varrer(HOJE)["total"] == 1


def test_idempotente_no_mesmo_dia() -> None:
    # Reexecutar o cron no mesmo dia não republica (guarda por (fatura_id, dia)).
    fid = uuid.uuid4()
    svc, bus, _ = _svc([_fatura(HOJE, fid=fid)])
    svc.varrer(HOJE)
    svc.varrer(HOJE)
    assert len(bus.published) == 1


def test_dispara_de_novo_em_outro_dia() -> None:
    # D-3 (29/05) e depois D-0 (01/06) da MESMA fatura geram 2 lembretes (dias distintos).
    fid = uuid.uuid4()
    venc = HOJE  # vence 01/06
    svc, bus, _ = _svc([_fatura(venc, fid=fid)])
    svc.varrer(venc - dt.timedelta(days=3))  # D-3
    svc.varrer(venc)  # D-0
    assert len(bus.published) == 2
    dias = sorted(p[1]["dados"]["dias_para_vencer"] for p in bus.published)
    assert dias == [0, 3]


def test_marcador_idempotencia_grava_titular_id() -> None:
    # O marcador insert-only nasce já chaveado por titular_id (R-12).
    svc, _, mem = _svc([_fatura(HOJE)])
    svc.varrer(HOJE)
    itens = mem.list_for_titular(TID)
    assert itens and itens[0].titular_id == TID


def test_template_lembrete_d3_e_d0_diferentes() -> None:
    base = dict(
        tipo="pagamento", subtipo="lembrete", telefone=TELEFONE, nome="Edgar Damasceno",
    )
    ev_d3 = EventoCX(
        **base, idempotency_key="k3",
        dados={"mes": "2026-06", "valor": "R$ 268,69", "vencimento": "2026-06-04",
               "dias_para_vencer": 3},
    )
    ev_d0 = EventoCX(
        **base, idempotency_key="k0",
        dados={"mes": "2026-06", "valor": "R$ 268,69", "vencimento": "2026-06-01",
               "dias_para_vencer": 0},
    )
    txt_d3 = render_notificacao(ev_d3)
    txt_d0 = render_notificacao(ev_d0)
    assert "Edgar" in txt_d3 and "R$ 268,69" in txt_d3
    assert "vence em 3 dias" in txt_d3
    assert "vence hoje" in txt_d0
    assert txt_d3 != txt_d0


def test_evento_lembrete_subject_e_memoria_chave() -> None:
    ev = EventoCX(
        tipo="pagamento", subtipo="lembrete", telefone=TELEFONE, nome="Edgar",
        idempotency_key="k", dados={},
    )
    assert ev.subject == "utilitycx.pagamento.lembrete"
    assert ev.memoria_chave == "proativo.pagamento.lembrete"


def test_entrypoint_executar_chama_varrer(monkeypatch: Any) -> None:
    # Entrypoint do cron (python -m src.infrastructure.events.reminder): monta o serviço
    # e chama varrer(hoje) — sem tocar DB/NATS/Omni (monkeypatch da montagem).
    from types import SimpleNamespace

    import src.infrastructure.events.reminder as reminder

    chamadas: list[dt.date] = []

    class FakeSvc:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def varrer(self, hoje: dt.date) -> dict[str, object]:
            chamadas.append(hoje)
            return {"data": hoje.isoformat(), "lembretes": [], "total": 0}

    monkeypatch.setattr(reminder, "ProactiveReminderService", FakeSvc)
    monkeypatch.setattr(reminder, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

    r = reminder.executar(HOJE)
    assert chamadas == [HOJE]
    assert r["total"] == 0 and r["data"] == HOJE.isoformat()
