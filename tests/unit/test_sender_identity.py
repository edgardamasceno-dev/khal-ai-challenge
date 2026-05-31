"""Resolução de identidade do remetente: LID + nono dígito (SPEC-015)."""

from __future__ import annotations

import uuid

import pytest

from src.application.services import BillingService
from src.domain.billing.entities import Titular
from src.domain.shared.errors import NotFoundError
from src.domain.shared.value_objects import CPF, Telefone
from src.infrastructure.events.omni_chats import HttpxOmniChats
from tests.unit.fakes import (
    FakeFaturaRepository,
    FakeTitularRepository,
    FakeUnidadeRepository,
    FakeUnitOfWork,
)

TID = uuid.uuid4()


class _FakeDirectory:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._m = mapping

    def resolve_canonical(self, external_id: str) -> str | None:
        return self._m.get(external_id)


def _svc(cadastro: str = "5581993112159", directory: object = None) -> BillingService:
    titular = Titular(
        id=TID, nome="Edgar", cpf=CPF("52998224725"),
        telefone=Telefone(cadastro), email=None, persona_key="edgar",
    )
    return BillingService(
        FakeTitularRepository([titular]),
        FakeUnidadeRepository(),
        FakeFaturaRepository(),
        FakeUnitOfWork(),
        directory=directory,  # type: ignore[arg-type]
    )


class TestFindCustomerIdentity:
    def test_telefone_exato(self) -> None:
        assert _svc().find_customer_by_phone("5581993112159").nome == "Edgar"

    def test_nono_digito(self) -> None:
        # cadastro com 9; remetente (canonical do WhatsApp) sem 9
        assert _svc().find_customer_by_phone("558193112159").nome == "Edgar"

    def test_lid_resolvido_pelo_omni(self) -> None:
        svc = _svc(directory=_FakeDirectory({"87866608713902@lid": "558193112159"}))
        assert svc.find_customer_by_phone("87866608713902@lid").nome == "Edgar"

    def test_sufixo_whatsapp_ignorado(self) -> None:
        assert _svc().find_customer_by_phone("5581993112159@s.whatsapp.net").nome == "Edgar"

    def test_desconhecido_sem_diretorio_404(self) -> None:
        with pytest.raises(NotFoundError):
            _svc().find_customer_by_phone("550000000000")

    def test_lid_sem_mapeamento_404(self) -> None:
        svc = _svc(directory=_FakeDirectory({}))
        with pytest.raises(NotFoundError):
            svc.find_customer_by_phone("99999999999999@lid")


def _chats(handler):  # type: ignore[no-untyped-def]
    h = HttpxOmniChats("http://omni", api_key="k", instance_id="i1")
    h._fetch_chats = handler  # type: ignore[assignment,method-assign]
    return h


class TestHttpxOmniChats:
    def test_casa_externalid_e_normaliza_canonical(self) -> None:
        h = _chats(lambda: [
            {"externalId": "0@s.whatsapp.net", "canonicalId": "0"},
            {"externalId": "87866608713902@lid", "canonicalId": "558193112159@s.whatsapp.net"},
        ])
        assert h.resolve_canonical("87866608713902@lid") == "558193112159"

    def test_sem_match_none(self) -> None:
        h = _chats(lambda: [{"externalId": "111@lid", "canonicalId": "55@s.whatsapp.net"}])
        assert h.resolve_canonical("87866608713902@lid") is None

    def test_sem_instancia_none(self) -> None:
        assert HttpxOmniChats("http://omni", instance_id="").resolve_canonical("x@lid") is None

    def test_omni_inacessivel_none(self) -> None:
        def boom() -> list[dict]:  # type: ignore[type-arg]
            raise RuntimeError("sem rota")

        assert _chats(boom).resolve_canonical("87866608713902@lid") is None


class TestChannelControl:
    """pausar/retomar resolve o chat id por external/canonical (SPEC-016)."""

    _CHATS = [
        {"id": "chat-uuid", "externalId": "87866608713902@lid",
         "canonicalId": "558193112159@s.whatsapp.net"},
    ]

    def test_chat_id_por_lid(self) -> None:
        h = _chats(lambda: self._CHATS)
        assert h._chat_id("87866608713902@lid") == "chat-uuid"

    def test_chat_id_por_telefone_com_9(self) -> None:
        # remetente com 9 casa o canonical sem 9 (variantes)
        h = _chats(lambda: self._CHATS)
        assert h._chat_id("5581993112159") == "chat-uuid"

    def test_sem_match_none(self) -> None:
        h = _chats(lambda: self._CHATS)
        assert h._chat_id("550000000000") is None

    def test_retomar_usa_clear_session_com_external_id(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        # SPEC-016: retomar reseta a sessão (clear-session), não só a flag.
        chamadas: list[tuple[str, dict]] = []  # type: ignore[type-arg]

        class _Resp:
            def raise_for_status(self) -> None: ...

        class _Client:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self
            def __exit__(self, *a: object) -> None: ...
            def post(self, url: str, json: dict) -> _Resp:  # type: ignore[type-arg]
                chamadas.append((url, json))
                return _Resp()
            def patch(self, url: str, json: dict) -> _Resp:  # type: ignore[type-arg]
                chamadas.append((url, json))
                return _Resp()

        monkeypatch.setattr(
            "src.infrastructure.events.omni_chats.httpx.Client", lambda **k: _Client()
        )
        h = _chats(lambda: self._CHATS)
        assert h.retomar_agente("5581993112159") is True
        url, body = chamadas[-1]
        assert url.endswith("/api/v2/chats/clear-session")
        assert body == {"instanceId": "i1", "chatId": "87866608713902@lid"}

    def test_pausar_usa_patch_agentpaused(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        capturado: dict = {}  # type: ignore[type-arg]

        class _Resp:
            def raise_for_status(self) -> None: ...

        class _Client:
            def __enter__(self):  # type: ignore[no-untyped-def]
                return self
            def __exit__(self, *a: object) -> None: ...
            def patch(self, url: str, json: dict) -> _Resp:  # type: ignore[type-arg]
                capturado["url"] = url
                capturado["json"] = json
                return _Resp()

        monkeypatch.setattr(
            "src.infrastructure.events.omni_chats.httpx.Client", lambda **k: _Client()
        )
        h = _chats(lambda: self._CHATS)
        assert h.pausar_agente("5581993112159") is True
        assert capturado["url"].endswith("/api/v2/chats/chat-uuid")
        assert capturado["json"] == {"settings": {"agentPaused": True}}
