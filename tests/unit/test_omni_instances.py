"""SPEC-030: resolução do instance-id do Omni pelo NOME estável (sem fixar UUID no .env)."""

from __future__ import annotations

import httpx

from src.infrastructure.events.omni_instances import resolve_instance_id
from src.infrastructure.events.omni_sender import HttpxOmniSender


def _instances(items: list[dict]) -> httpx.MockTransport:  # type: ignore[type-arg]
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v2/instances"
        return httpx.Response(200, json={"items": items})

    return httpx.MockTransport(handler)


class TestResolveInstanceId:
    def test_casa_por_nome(self) -> None:
        t = _instances([{"id": "aaa", "name": "outro"}, {"id": "bbb", "name": "luzdovale-bot"}])
        assert resolve_instance_id("http://omni", {}, "luzdovale-bot", transport=t) == "bbb"

    def test_sem_match_cai_na_primeira(self) -> None:
        t = _instances([{"id": "aaa", "name": "x"}])
        assert resolve_instance_id("http://omni", {}, "naoexiste", transport=t) == "aaa"

    def test_lista_vazia_none(self) -> None:
        assert (
            resolve_instance_id("http://omni", {}, "luzdovale-bot", transport=_instances([]))
            is None
        )

    def test_nome_vazio_none(self) -> None:
        assert resolve_instance_id("http://omni", {}, "") is None

    def test_omni_inacessivel_none(self) -> None:
        def boom(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("sem rota")

        assert (
            resolve_instance_id(
                "http://omni", {}, "luzdovale-bot", transport=httpx.MockTransport(boom)
            )
            is None
        )


class TestClientsResolvemPorNome:
    """Os adapters resolvem o instance-id pelo nome quando OMNI_INSTANCE_ID está vazio (lazy)."""

    def test_sender_eid_resolve(self) -> None:
        s = HttpxOmniSender(
            "http://omni",
            instance_id="",
            instance_name="luzdovale-bot",
            transport=_instances([{"id": "INST1", "name": "luzdovale-bot"}]),
        )
        assert s._eid() == "INST1"
        # cacheado: vira o instance_id do client
        assert s._instance_id == "INST1"

    def test_sender_id_fixo_tem_precedencia(self) -> None:
        # Com OMNI_INSTANCE_ID setado, NÃO consulta o Omni (override).
        s = HttpxOmniSender("http://omni", instance_id="FIXO", instance_name="luzdovale-bot")
        assert s._eid() == "FIXO"
