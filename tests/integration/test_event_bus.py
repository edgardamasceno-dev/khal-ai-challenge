"""Teste de integração do NatsEventBus (SPEC-009) contra NATS efêmero."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from src.infrastructure.events.nats_bus import NatsEventBus

pytestmark = pytest.mark.skipif(
    not os.environ.get("NATS_URL"), reason="NATS_URL nao definido"
)


def test_publish_round_trip() -> None:
    url = os.environ["NATS_URL"]
    received: list[tuple[str, dict]] = []

    async def run() -> None:
        import nats

        nc = await nats.connect(url)
        fut: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

        async def cb(msg: object) -> None:
            received.append((msg.subject, json.loads(msg.data)))  # type: ignore[attr-defined]
            if not fut.done():
                fut.set_result(True)

        await nc.subscribe("utilitycx.>", cb=cb)
        # publish síncrono (asyncio.run interno) numa thread separada -> sem loop aninhado.
        await asyncio.to_thread(
            NatsEventBus(url).publish, "utilitycx.pagamento.confirmado", {"tipo": "pagamento"}
        )
        await asyncio.wait_for(fut, timeout=5)
        await nc.close()

    asyncio.run(run())
    assert received and received[0][0] == "utilitycx.pagamento.confirmado"
    assert received[0][1]["tipo"] == "pagamento"
