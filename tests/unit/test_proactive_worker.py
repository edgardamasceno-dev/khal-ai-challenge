"""Teste do worker de notificações (SPEC-009): consome evento -> processa."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import src.infrastructure.events.worker as worker


def test_handle_reconstroi_evento_e_processa(monkeypatch: Any) -> None:
    chamadas: list[Any] = []

    class FakeSvc:
        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        def processar(self, evento: Any) -> dict[str, object]:
            chamadas.append(evento)
            return {"enviado": True}

    # Evita tocar em DB/NATS/Omni: troca a montagem do serviço e a sessão.
    monkeypatch.setattr(worker, "ProactiveService", FakeSvc)
    monkeypatch.setattr(worker, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

    payload = {
        "tipo": "pagamento", "subtipo": "confirmado", "telefone": "5581993112159",
        "nome": "Edgar", "idempotency_key": "k1", "dados": {"mes": "05/2026"},
    }
    msg = SimpleNamespace(data=json.dumps(payload).encode())
    asyncio.run(worker._handle(msg))

    assert len(chamadas) == 1
    assert chamadas[0].subject == "utilitycx.pagamento.confirmado"
    assert chamadas[0].nome == "Edgar"
