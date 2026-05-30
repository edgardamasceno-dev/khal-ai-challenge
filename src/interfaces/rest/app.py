"""Fabrica da API REST do sistema legado (Luz do Vale).

Sobe atras do gateway em /api (root_path). Expoe os endpoints que o
mcp-server consome (server-to-server). Hexagonal: interfaces -> application
-> domain, com infrastructure implementando os ports.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.interfaces.rest.exception_handlers import register_exception_handlers
from src.interfaces.rest.routers import (
    billing,
    conversation,
    health,
    knowledge,
    outage,
    ticketing,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Luz do Vale - API Legado",
        version="0.2.0",
        summary="Sistema legado simulado: dados e acoes de CX de energia.",
        root_path="/api",
    )
    register_exception_handlers(app)
    for module in (health, billing, outage, ticketing, conversation, knowledge):
        app.include_router(module.router)
    return app


app = create_app()
