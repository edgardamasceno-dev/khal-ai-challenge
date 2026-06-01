"""Worker de notificações proativas (SPEC-009 / ADR-0005).

Assina `utilitycx.>` no NATS e processa cada evento deterministicamente
(render -> Omni -> conversation_memory). **Sem LLM** no caminho.

Roteamento por wildcard: qualquer (tipo, subtipo) válido cai aqui sem código novo —
inclui o lembrete de vencimento `utilitycx.pagamento.lembrete` publicado pelo cron
ProactiveReminderService (R-16 / SPEC-026), renderizado pelo template canônico.

    python -m src.infrastructure.events.worker
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.application.services import ProactiveService
from src.config import settings
from src.domain.notifications.entities import EventoCX
from src.infrastructure.db import SessionLocal
from src.infrastructure.events.nats_bus import NatsEventBus
from src.infrastructure.events.omni_sender import HttpxOmniSender
from src.infrastructure.repositories import (
    SqlAlchemyUnitOfWork,
    SqlFaturaRepository,
    SqlInterrupcaoRepository,
    SqlMemoriaRepository,
    SqlTitularRepository,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("proactive.worker")


def _evento(data: dict[str, Any]) -> EventoCX:
    return EventoCX(
        tipo=data["tipo"],
        subtipo=data["subtipo"],
        telefone=data["telefone"],
        nome=data["nome"],
        idempotency_key=data["idempotency_key"],
        dados=data.get("dados", {}),
    )


async def _handle(msg: object) -> None:
    data = json.loads(msg.data)  # type: ignore[attr-defined]
    evento = _evento(data)
    session = SessionLocal()
    try:
        svc = ProactiveService(
            NatsEventBus(settings.nats_url),
            HttpxOmniSender(
                settings.omni_url,
                settings.omni_api_key,
                settings.omni_instance_id,
                settings.omni_instance_name,
            ),
            SqlMemoriaRepository(session),
            SqlTitularRepository(session),
            SqlFaturaRepository(session),
            SqlInterrupcaoRepository(session),
            SqlAlchemyUnitOfWork(session),
        )
        res = svc.processar(evento)
        logger.info("processado %s -> enviado=%s", evento.subject, res["enviado"])
    except Exception:
        logger.exception("falha ao processar %s", evento.subject)
    finally:
        session.close()


async def run() -> None:
    import nats

    nc = await nats.connect(settings.nats_url)
    await nc.subscribe("utilitycx.>", cb=_handle)
    logger.info("worker ouvindo utilitycx.> em %s", settings.nats_url)
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(run())
