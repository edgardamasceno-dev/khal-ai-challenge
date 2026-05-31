"""OperatorChatService + adapter de transcript (SPEC-018)."""

from __future__ import annotations

import datetime as dt

from src.application.services import OperatorChatService
from src.domain.conversation.entities import MensagemChat
from src.infrastructure.events.omni_chats import HttpxOmniChats
from tests.unit.fakes import FakeChannelControl, FakeChatTranscript, FakeOmniSender

NOW = dt.datetime(2026, 5, 31, 3, tzinfo=dt.UTC)


def _svc(
    itens: list[MensagemChat] | None = None, tem_mais: bool = False
) -> tuple[OperatorChatService, FakeChannelControl, FakeOmniSender]:
    control, sender = FakeChannelControl(), FakeOmniSender()
    svc = OperatorChatService(FakeChatTranscript(itens, tem_mais), control, sender)
    return svc, control, sender


class TestOperatorChatService:
    def test_transcript_devolve_mensagens_e_paginacao(self) -> None:
        msgs = [MensagemChat(id=str(i), texto=f"m{i}", do_cliente=i % 2 == 0, em=NOW)
                for i in range(3)]
        svc, _, _ = _svc(msgs, tem_mais=True)
        itens, cursor, tem_mais = svc.transcript("5581993112159", limit=10, cursor=None)
        assert len(itens) == 3 and tem_mais is True
        assert cursor == "cur"

    def test_takeover_pausa_e_status(self) -> None:
        svc, control, _ = _svc()
        assert svc.status("5581993112159")["pausado"] is False
        assert svc.takeover("5581993112159")["pausado"] is True
        assert control.pausados == ["5581993112159"]
        assert svc.status("5581993112159")["pausado"] is True

    def test_release_retoma(self) -> None:
        svc, control, _ = _svc()
        svc.takeover("5581993112159")
        assert svc.release("5581993112159")["pausado"] is False
        assert control.retomados == ["5581993112159"]

    def test_send_usa_o_sender(self) -> None:
        svc, _, sender = _svc()
        assert svc.send("5581993112159", "olá")["enviado"] is True
        assert sender.enviados == [("5581993112159", "olá")]


def _chats(handler):  # type: ignore[no-untyped-def]
    h = HttpxOmniChats("http://omni", api_key="k", instance_id="i1")
    h._chat_id = lambda remetente: "chat-uuid"  # type: ignore[assignment,method-assign]
    h._fetch = handler  # type: ignore[attr-defined]
    return h


class TestTranscriptAdapter:
    def test_mapeia_campos_e_inverte_fromMe(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        h = HttpxOmniChats("http://omni", api_key="k", instance_id="i1")
        monkeypatch.setattr(h, "_chat_id", lambda r: "chat-uuid")
        payload = {
            "items": [
                {"id": "a", "textContent": "oi do bot", "isFromMe": True,
                 "platformTimestamp": "2026-05-31T03:43:53.757Z", "hasMedia": False},
                {"id": "b", "textContent": "oi do cliente", "isFromMe": False,
                 "platformTimestamp": "2026-05-31T03:43:40.000Z", "hasMedia": False},
            ],
            "meta": {"hasMore": True, "cursor": "2026-05-31T03:43:40.000Z"},
        }

        class _Resp:
            def raise_for_status(self) -> None: ...
            def json(self) -> dict:  # type: ignore[type-arg]
                return payload

        class _Client:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self
            def __exit__(self, *a: object) -> None: ...
            def get(self, *a: object, **k: object) -> _Resp:
                return _Resp()

        monkeypatch.setattr(
            "src.infrastructure.events.omni_chats.httpx.Client", lambda **k: _Client()
        )
        itens, cursor, tem_mais = h.mensagens("5581993112159", 10, None)
        assert [m.texto for m in itens] == ["oi do bot", "oi do cliente"]
        assert itens[0].do_cliente is False and itens[1].do_cliente is True
        assert tem_mais is True and cursor == "2026-05-31T03:43:40.000Z"

    def test_sem_chat_id_vazio(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        h = HttpxOmniChats("http://omni", api_key="k", instance_id="i1")
        monkeypatch.setattr(h, "_chat_id", lambda r: None)
        assert h.mensagens("x", 10, None) == ([], None, False)
