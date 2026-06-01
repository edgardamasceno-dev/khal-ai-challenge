"""Testes do resumo de thread no fechamento (R-15 / SPEC-028 / ADR-0019).

Cobre:
- `resumo_extrativo` (domínio puro, determinístico, sem mock);
- `ThreadSummaryService` com `SummarizerPort` de sucesso (fonte=haiku);
- adapter que levanta -> cai no fallback extrativo (falha NÃO propaga);
- `summarizer=None` -> usa o extrativo;
- gravação `kind=resumo` no JSONB `valor` (ADR-0013);
- disparo best-effort acoplado em `resolve_ticket`/`resume_handoff`.
"""

from __future__ import annotations

import datetime as dt
import uuid

from src.application.ports import SummarizerError
from src.application.services import ThreadSummaryService, TicketingService
from src.domain.billing.entities import Titular
from src.domain.conversation.entities import MensagemChat
from src.domain.conversation.summarize import resumo_extrativo
from src.domain.shared.value_objects import CPF, StatusChamado, Telefone, TipoChamado
from src.domain.ticketing.entities import Chamado, Handoff
from tests.unit.fakes import (
    FakeChamadoRepository,
    FakeChatTranscript,
    FakeHandoffRepository,
    FakeMemoriaRepository,
    FakeTitularRepository,
    FakeUnitOfWork,
)

ANA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ANA_TEL = "555199990001"


def _ana() -> Titular:
    return Titular(
        id=ANA_ID,
        nome="Ana Souza",
        cpf=CPF("52998224725"),
        telefone=Telefone(ANA_TEL),
        email=None,
        persona_key="ana.souza",
    )


def _msgs() -> list[MensagemChat]:
    base = dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC)
    return [
        MensagemChat("1", "Minha luz caiu no Jardim das Flores", True, base),
        MensagemChat("2", "Sinto muito! Há uma interrupção ativa na sua região.", False, base),
        MensagemChat("3", "E quando volta?", True, base),
        MensagemChat("4", "Previsão de retorno até 18h. Abri o chamado AB-001.", False, base),
        MensagemChat("5", "Obrigada!", True, base),
    ]


def _clock() -> dt.datetime:
    return dt.datetime(2026, 5, 31, 15, 0, tzinfo=dt.UTC)


# --- Fakes locais do SummarizerPort ----------------------------------------


class FakeSummarizer:
    """Adapter de resumo que devolve um texto fixo (caminho feliz)."""

    def __init__(self, texto: str = "Resumo via LLM.") -> None:
        self.texto = texto
        self.chamadas = 0

    def summarize(self, mensagens: list[MensagemChat], *, max_chars: int = 600) -> str:
        self.chamadas += 1
        return self.texto


class RaisingSummarizer:
    """Adapter que SEMPRE falha (timeout/empty) -> serviço cai no fallback."""

    def __init__(self) -> None:
        self.chamadas = 0

    def summarize(self, mensagens: list[MensagemChat], *, max_chars: int = 600) -> str:
        self.chamadas += 1
        raise SummarizerError("boom")


# --- resumo_extrativo (puro) -----------------------------------------------


def test_extrativo_e_deterministico_e_idempotente() -> None:
    msgs = _msgs()
    a = resumo_extrativo(msgs)
    b = resumo_extrativo(msgs)
    assert a == b  # idempotente
    assert "[cliente] Minha luz caiu" in a  # 1ª do cliente (motivo)
    assert "[agente]" in a  # inclui o desfecho do atendente


def test_extrativo_respeita_max_chars() -> None:
    msgs = _msgs()
    resumo = resumo_extrativo(msgs, max_chars=40)
    assert len(resumo) <= 40


def test_extrativo_sem_conteudo() -> None:
    assert resumo_extrativo([]) == "[sem conteúdo de conversa]"
    vazio = [MensagemChat("1", "   ", True, _clock())]
    assert resumo_extrativo(vazio) == "[sem conteúdo de conversa]"


# --- ThreadSummaryService ---------------------------------------------------


def _service(summarizer: object | None) -> tuple[ThreadSummaryService, FakeMemoriaRepository]:
    memorias = FakeMemoriaRepository()
    svc = ThreadSummaryService(
        transcript=FakeChatTranscript(_msgs()),
        memorias=memorias,
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        summarizer=summarizer,  # type: ignore[arg-type]
        clock=_clock,
    )
    return svc, memorias


def test_summarize_usa_llm_quando_sucesso() -> None:
    fake = FakeSummarizer("Cliente relatou queda de energia; chamado aberto.")
    svc, memorias = _service(fake)

    out = svc.summarize_thread(ANA_TEL, protocolo="AB-001")

    assert fake.chamadas == 1
    assert out["fonte"] == "haiku"
    assert out["resumo"] == "Cliente relatou queda de energia; chamado aberto."
    assert out["gravado"] is True
    registros = memorias.list_for_titular(ANA_ID)
    assert len(registros) == 1
    valor = registros[0].valor
    assert valor["kind"] == "resumo"
    assert valor["fonte"] == "haiku"
    assert registros[0].chave == "resumo.AB-001"
    assert registros[0].titular_id == ANA_ID


def test_summarize_cai_no_fallback_quando_llm_falha() -> None:
    raising = RaisingSummarizer()
    svc, memorias = _service(raising)

    out = svc.summarize_thread(ANA_TEL, protocolo="AB-002")

    assert raising.chamadas == 1  # tentou o LLM
    assert out["fonte"] == "extrativo"  # mas caiu no determinístico
    assert "[cliente] Minha luz caiu" in out["resumo"]
    registros = memorias.list_for_titular(ANA_ID)
    assert registros[0].valor["fonte"] == "extrativo"
    assert registros[0].valor["kind"] == "resumo"


def test_summarize_sem_summarizer_usa_extrativo() -> None:
    svc, memorias = _service(None)

    out = svc.summarize_thread(ANA_TEL, protocolo="AB-003")

    assert out["fonte"] == "extrativo"
    assert out["resumo"] == resumo_extrativo(_msgs())


def test_summarize_telefone_desconhecido_grava_por_chat() -> None:
    """Sem titular resolvido, grava por chat_id (titular_id None) — não quebra."""
    svc, memorias = _service(None)

    out = svc.summarize_thread("550000000000", protocolo=None)

    assert out["gravado"] is True
    # chave por ts (sem protocolo) — registro existe no store por chat
    registros = memorias.list_for_chat("550000000000")
    assert len(registros) == 1
    assert registros[0].titular_id is None
    assert registros[0].chave.startswith("resumo.")


def test_summarize_thread_safe_engole_falha() -> None:
    """A variante segura não propaga falha de persistência nem exige telefone."""

    class BoomMemoria(FakeMemoriaRepository):
        def upsert(self, *a: object, **k: object):  # type: ignore[no-untyped-def]
            raise RuntimeError("db down")

    svc = ThreadSummaryService(
        transcript=FakeChatTranscript(_msgs()),
        memorias=BoomMemoria(),
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        summarizer=None,
        clock=_clock,
    )
    # Não levanta, mesmo com a persistência quebrada.
    svc.summarize_thread_safe(ANA_TEL, "AB-004")
    # No-op sem telefone.
    svc.summarize_thread_safe(None, "AB-004")


# --- Disparo best-effort no fechamento -------------------------------------


def _chamado() -> Chamado:
    agora = _clock()
    return Chamado(
        id=uuid.uuid4(),
        protocolo="AB-2026-0001",
        titular_id=ANA_ID,
        uc_id=None,
        tipo=TipoChamado.falta_energia,
        descricao=None,
        status=StatusChamado.aberto.value,
        sla_horas=24,
        canal="whatsapp",
        aberto_em=agora,
        atualizado_em=agora,
    )


def _ticketing(
    thread_summary: ThreadSummaryService | None,
) -> TicketingService:
    return TicketingService(
        chamados=FakeChamadoRepository([_chamado()]),
        handoffs=FakeHandoffRepository(),
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        thread_summary=thread_summary,
    )


def test_resolve_ticket_dispara_resumo_best_effort() -> None:
    memorias = FakeMemoriaRepository()
    summary = ThreadSummaryService(
        transcript=FakeChatTranscript(_msgs()),
        memorias=memorias,
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        summarizer=None,
        clock=_clock,
    )
    ticketing = TicketingService(
        chamados=FakeChamadoRepository([_chamado()]),
        handoffs=FakeHandoffRepository(),
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        thread_summary=summary,
    )

    ticketing.resolve_ticket("AB-2026-0001")

    registros = memorias.list_for_titular(ANA_ID)
    assert any(r.valor.get("kind") == "resumo" for r in registros)
    assert registros[0].chave == "resumo.AB-2026-0001"


def test_resolve_ticket_sem_summary_nao_quebra() -> None:
    ticketing = _ticketing(None)
    chamado = ticketing.resolve_ticket("AB-2026-0001")
    assert chamado.status == StatusChamado.resolvido.value


def test_resolve_ticket_falha_no_resumo_nao_bloqueia_fechamento() -> None:
    """O resumo é best-effort: uma falha de persistência sua NÃO impede o ticket
    de resolver. O blindar (engolir) fica em `summarize_thread_safe`."""

    class BoomMemoria(FakeMemoriaRepository):
        def upsert(self, *a: object, **k: object):  # type: ignore[no-untyped-def]
            raise RuntimeError("db do resumo down")

    summary = ThreadSummaryService(
        transcript=FakeChatTranscript(_msgs()),
        memorias=BoomMemoria(),
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        summarizer=None,
        clock=_clock,
    )
    ticketing = TicketingService(
        chamados=FakeChamadoRepository([_chamado()]),
        handoffs=FakeHandoffRepository(),
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        thread_summary=summary,
    )

    # O ticket resolve normalmente mesmo com o resumo explodindo na persistência.
    chamado = ticketing.resolve_ticket("AB-2026-0001")
    assert chamado.status == StatusChamado.resolvido.value


def test_resume_handoff_dispara_resumo() -> None:
    memorias = FakeMemoriaRepository()
    summary = ThreadSummaryService(
        transcript=FakeChatTranscript(_msgs()),
        memorias=memorias,
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        summarizer=None,
        clock=_clock,
    )
    handoffs = FakeHandoffRepository()
    h = Handoff(
        id=uuid.uuid4(),
        chamado_id=None,
        motivo="cliente pediu humano",
        status="pendente",
        operador=None,
        criado_em=_clock(),
        remetente=ANA_TEL,
    )
    handoffs.add(h)
    ticketing = TicketingService(
        chamados=FakeChamadoRepository(),
        handoffs=handoffs,
        titulares=FakeTitularRepository([_ana()]),
        uow=FakeUnitOfWork(),
        thread_summary=summary,
    )

    ticketing.resume_handoff(h.id, operador="op1")

    registros = memorias.list_for_titular(ANA_ID)
    assert any(r.valor.get("kind") == "resumo" for r in registros)
