"""Fixtures de integracao: sessao transacional (rollback por teste) contra o
Postgres efemero de teste (schema da SPEC-000, sem seed).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from src.infrastructure.db import engine


@pytest.fixture
def session() -> Iterator[Session]:
    connection = engine.connect()
    trans = connection.begin()
    sess = Session(bind=connection)
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        connection.close()
