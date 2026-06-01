"""Cron de lembretes proativos de vencimento D-3/D-0 (R-16 / SPEC-026).

DETERMINÍSTICO, sem LLM. NÃO roda no worker de notificação (que só consome
`utilitycx.>`): é um entrypoint próprio de backend (tem repos + UoW) que varre as
faturas em aberto/vencida e publica `utilitycx.pagamento.lembrete` para os
vencimentos em D-3 e D-0 do dia. O worker existente renderiza, envia (Omni) e grava
na memória. Idempotente por (fatura_id, dia).

    python -m src.infrastructure.events.reminder

Pensado para um agendamento externo (cron do compose/host) que dispara uma vez por
dia; reexecutar no mesmo dia não duplica lembretes.
"""

from __future__ import annotations

import datetime as dt
import logging

from src.application.services import ProactiveReminderService
from src.config import settings
from src.infrastructure.db import SessionLocal
from src.infrastructure.events.nats_bus import NatsEventBus
from src.infrastructure.repositories import (
    SqlAlchemyUnitOfWork,
    SqlFaturaRepository,
    SqlMemoriaRepository,
    SqlTitularRepository,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("proactive.reminder")

# Fuso fixo de Brasília (sem DST desde 2019); espelha src/domain/notifications/templates.
_BRT = dt.timezone(dt.timedelta(hours=-3))


def hoje_local() -> dt.date:
    """Data local (America/São_Paulo) para casar D-3/D-0 sem deslize de fuso."""
    return dt.datetime.now(_BRT).date()


def executar(hoje: dt.date | None = None) -> dict[str, object]:
    """Monta o serviço contra os repos reais e varre os lembretes do dia."""
    session = SessionLocal()
    try:
        svc = ProactiveReminderService(
            NatsEventBus(settings.nats_url),
            SqlMemoriaRepository(session),
            SqlTitularRepository(session),
            SqlFaturaRepository(session),
            SqlAlchemyUnitOfWork(session),
        )
        resultado = svc.varrer(hoje or hoje_local())
        logger.info("lembretes %s -> publicados=%s", resultado["data"], resultado["total"])
        return resultado
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover
    executar()
