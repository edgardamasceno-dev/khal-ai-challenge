"""Entrypoint do seeder: `python -m src.infrastructure.seed` (ADR-0008).

Lê `SEED_PERSONAS` / `SEED_RANDOM_SEED` / `SEED_HISTORY_MONTHS` do ambiente,
deriva os perfis e materializa a massa (idempotente). Roda após o `database`
saudável (serviço one-shot no compose).
"""

from __future__ import annotations

import os
import sys

from src.application.persona_registry import carregar_personas
from src.infrastructure.db import SessionLocal
from src.infrastructure.seed import seed_personas


def main() -> int:
    raw = os.environ.get("SEED_PERSONAS", "")
    seed = int(os.environ.get("SEED_RANDOM_SEED", "42"))
    months = int(os.environ.get("SEED_HISTORY_MONTHS", "24"))

    try:
        personas = carregar_personas(raw, seed)
    except ValueError as exc:
        print(f"[seed] SEED_PERSONAS invalido: {exc}", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        rep = seed_personas(session, personas, history_months=months)
        session.commit()

    print(
        f"[seed] personas={len(personas)} titulares=+{rep.titulares} "
        f"unidades=+{rep.unidades} faturas=+{rep.faturas} "
        f"pagamentos=+{rep.pagamentos} interrupcoes=+{rep.interrupcoes} "
        f"chamados=+{rep.chamados}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
