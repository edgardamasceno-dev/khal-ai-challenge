"""MCP server (FastMCP, streamable-HTTP). Expoe as ferramentas ao agente
(Genie/Claude Code), delegando para CxTools sobre a API legada (MCP-over-REST).

`phone` representa o telefone do remetente: no wiring real e injetado pelo
canal/Omni (contexto confiavel), nao e input livre do agente.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.interfaces.mcp.client import HttpxLegacyApiClient
from src.interfaces.mcp.tools import CxTools

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

_tools = CxTools(HttpxLegacyApiClient(BACKEND_URL))
mcp = FastMCP("luz-do-vale", host="0.0.0.0", port=8000)


@mcp.tool()
def find_customer_by_phone(phone: str) -> dict[str, Any]:
    """Identifica o titular pelo telefone do remetente. Use sempre primeiro."""
    return _tools.find_customer_by_phone(phone)


@mcp.tool()
def list_contracts(phone: str) -> dict[str, Any]:
    """Lista as unidades consumidoras (UCs) do titular identificado pelo telefone."""
    return _tools.list_contracts(phone)


@mcp.tool()
def get_invoice_status(phone: str) -> dict[str, Any]:
    """Faturas em aberto/vencidas do titular (por telefone). Para segunda via/pagamento."""
    return _tools.get_invoice_status(phone)


@mcp.tool()
def get_outage_by_region(bairro: str) -> dict[str, Any]:
    """Verifica se ha interrupcao de energia ativa em um bairro."""
    return _tools.get_outage_by_region(bairro)


@mcp.tool()
def create_ticket(phone: str, tipo: str, descricao: str, confirmar: bool = False) -> dict[str, Any]:
    """Abre um chamado para o titular (por telefone). Requer confirmacao explicita.

    Chame com confirmar=false para revisar; depois confirmar=true para registrar.
    Idempotente: a mesma (telefone, tipo, descricao) nao duplica.
    tipo: falta_energia | religacao | segunda_via | titularidade | reclamacao.
    """
    return _tools.create_ticket(phone, tipo, descricao, confirmar)


@mcp.tool()
def get_ticket_status(phone: str, protocolo: str) -> dict[str, Any]:
    """Consulta o status de um chamado pelo protocolo (so do titular do telefone)."""
    return _tools.get_ticket_status(phone, protocolo)


@mcp.tool()
def request_human_handoff(phone: str, motivo: str) -> dict[str, Any]:
    """Escala o atendimento para um operador humano (fila do console)."""
    return _tools.request_human_handoff(phone, motivo)


@mcp.tool()
def search_knowledge_base(query: str) -> dict[str, Any]:
    """Busca na base de conhecimento (duvidas 'como faco para...').

    Responda fundamentado no `trecho` retornado e **cite o `slug`** da fonte.
    Nao afirme nada fora do que a busca devolveu.
    """
    return _tools.search_knowledge_base(query)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
