"""Adapter de EventBus em NATS (SPEC-009 / ADR-0005). Implementa EventBus.

Publish síncrono (conexão curta por chamada — eventos do operador são raros).
O consumo (worker) usa loop assíncrono próprio (events/worker.py).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


class NatsEventBus:
    def __init__(self, url: str) -> None:
        self._url = url

    def publish(self, subject: str, payload: dict[str, Any]) -> None:
        asyncio.run(self._publish(subject, payload))

    async def _publish(self, subject: str, payload: dict[str, Any]) -> None:
        import nats

        nc = await nats.connect(self._url)
        try:
            await nc.publish(subject, json.dumps(payload).encode())
            await nc.flush()
        finally:
            await nc.close()
