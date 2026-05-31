"""Integracao do sink de auditoria por tool-call (T3) contra o Postgres de
teste (khal_test). Insere/le um registro e comprova que o CHECK de
result_status (no schema, db/init/01-schema.sql) rejeita valores invalidos.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.ports import AuditRecord
from src.infrastructure.orm import ToolCallAuditORM
from src.infrastructure.repositories import SqlToolCallAuditSink


def test_insere_e_le_registro(session: Session) -> None:
    sink = SqlToolCallAuditSink(session)
    sink.record(
        AuditRecord(
            tool_name="find_customer_by_phone",
            result_status="ok",
            latency_ms=7,
            input_redacted={"phone": "****0001"},
            error_code=None,
            trace_id="trace-xyz",
            chat_id="chat-1",
        )
    )
    o = session.execute(
        select(ToolCallAuditORM).where(ToolCallAuditORM.tool_name == "find_customer_by_phone")
    ).scalar_one()
    assert o.result_status == "ok"
    assert o.latency_ms == 7
    assert o.input_redacted == {"phone": "****0001"}
    assert o.trace_id == "trace-xyz"
    assert o.error_code is None
    assert o.created_at is not None  # server_default now()
    # PII mascarada: nenhum telefone completo persistido.
    assert "555199990001" not in str(o.input_redacted)


def test_status_error_com_error_code(session: Session) -> None:
    SqlToolCallAuditSink(session).record(
        AuditRecord(
            tool_name="create_ticket",
            result_status="error",
            latency_ms=12,
            input_redacted={"phone": "****0001", "tipo": "falta_energia"},
            error_code="ValueError",
        )
    )
    o = session.execute(
        select(ToolCallAuditORM).where(ToolCallAuditORM.tool_name == "create_ticket")
    ).scalar_one()
    assert o.result_status == "error" and o.error_code == "ValueError"


def test_check_rejeita_status_invalido(session: Session) -> None:
    # O CHECK in ('ok','error','denied') esta no banco — valor invalido e rejeitado.
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO tool_call_audit (tool_name, result_status) "
                "VALUES ('x', 'invalido')"
            )
        )
        session.flush()
