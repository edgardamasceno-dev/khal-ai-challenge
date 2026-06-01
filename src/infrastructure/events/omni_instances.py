"""Resolução do UUID da instância do Omni pelo NOME estável (SPEC-030).

O `instanceId` do Omni é um UUID **gerado a cada pareamento** (`omni instances create`),
então fixá-lo no `.env` é frágil — muda em todo setup do zero. Aqui o backend o **descobre
em runtime**: `GET /api/v2/instances` e casa pelo `name` configurável (`OMNI_INSTANCE_NAME`,
default `luzdovale-bot`). Os adapters (sender/health/chats) chamam isto de forma LAZY (na 1ª
escrita/leitura que precisa do id), porque o pareamento acontece **depois** do startup.

Fallback determinístico: casa por nome -> primeira instância da lista -> None. Best-effort:
Omni inacessível -> None (o chamador degrada como já fazia com o id ausente).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("proactive.omni")


def resolve_instance_id(
    base_url: str,
    headers: dict[str, str],
    name: str,
    timeout: float = 3.0,
    transport: httpx.BaseTransport | None = None,
) -> str | None:
    """UUID da instância cujo `name` casa `name`; senão a 1ª; senão None."""
    if not name:
        return None
    try:
        kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
        if transport is not None:
            kwargs["transport"] = transport
        with httpx.Client(**kwargs) as client:
            r = client.get(f"{base_url.rstrip('/')}/api/v2/instances")
            r.raise_for_status()
            items: list[dict[str, Any]] = r.json().get("items", [])
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.info("não resolvi a instância '%s' por nome: %s", name, exc)
        return None
    por_nome = [it for it in items if it.get("name") == name]
    escolhida = por_nome[0] if por_nome else (items[0] if items else None)
    return (escolhida or {}).get("id") or None
