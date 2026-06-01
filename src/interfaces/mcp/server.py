"""MCP server (FastMCP, streamable-HTTP). Expoe as ferramentas ao agente
(Genie/Claude Code), delegando para CxTools sobre a API legada (MCP-over-REST).

`phone` representa o telefone do remetente: no wiring real e injetado pelo
canal/Omni (contexto confiavel), nao e input livre do agente.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.application.ports import AuditRecord, ToolCallAuditSink
from src.interfaces.mcp.audit import AuditedCxTools
from src.interfaces.mcp.client import HttpxLegacyApiClient
from src.interfaces.mcp.tools import CxTools

logger = logging.getLogger("luz_do_vale.mcp.server")

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")


class _SessionPerWriteAuditSink:
    """Sink de auditoria com sessao curta por escrita (T3).

    Abre uma sessao SQLAlchemy isolada por `record()` para nao acoplar a
    auditoria a transacao da tool. Se o DB nao estiver configurado/acessivel
    no boot (DATABASE_URL ausente), degrada para no-op (apenas-log). Falhas
    pontuais propagam para o RECORDER, que as engole (best-effort).
    """

    def __init__(self) -> None:
        # Import tardio: o MCP server roda mesmo sem DB no caminho da tool.
        from src.infrastructure.db import SessionLocal
        from src.infrastructure.repositories import SqlToolCallAuditSink

        self._SessionLocal = SessionLocal
        self._SqlSink = SqlToolCallAuditSink

    def record(self, registro: AuditRecord) -> None:
        with self._SessionLocal() as session:
            self._SqlSink(session).record(registro)


def _build_audit_sink() -> ToolCallAuditSink | None:
    """Constroi o sink de auditoria; degrada para None (apenas-log) se o DB
    nao estiver configurado. Nunca quebra o boot do MCP server."""
    try:
        return _SessionPerWriteAuditSink()
    except Exception:  # noqa: BLE001 — sem DB => observabilidade so por log.
        logger.warning("tool_call_audit sem persistencia (apenas-log)", exc_info=True)
        return None


_audit_sink = _build_audit_sink()
_tools = AuditedCxTools(CxTools(HttpxLegacyApiClient(BACKEND_URL)), sink=_audit_sink)
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
def generate_invoice_pdf(
    phone: str,
    presigned: bool = False,
    mes_referencia: str | None = None,
    numero_uc: str | None = None,
) -> dict[str, Any]:
    """Gera/envia o PDF (segunda via) de uma fatura do titular (PDF por midia, ADR-0003).

    Sem mes_referencia/numero_uc: a fatura atual (mais recente em aberto, senao a mais recente).
    Passe `mes_referencia` ('AAAA-MM') p/ uma fatura especifica, QUALQUER status (paga/vencida/em
    aberto, SPEC-031); e `numero_uc` p/ mirar a UC em multi-UC. Se a competencia existir em mais
    de uma unidade sem numero_uc, devolve `precisa_unidade` + as UCs. presigned=true -> link."""
    return _tools.generate_invoice_pdf(phone, presigned, mes_referencia, numero_uc)


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


@mcp.tool()
def get_account_events(phone: str) -> dict[str, Any]:
    """Le os FATOS DE SISTEMA da conta do titular (read-only) pelo telefone.

    Devolve eventos deterministicos ja registrados (ADR-0005): pagamento confirmado,
    interrupcao aberta/encerrada, ultimo protocolo. NAO e a transcricao da conversa
    (para isso use get_chat_history). Chame no PRIMEIRO turno (junto de
    find_customer_by_phone) para NAO reoferecer o que o sistema ja resolveu.
    Nao escreve nem muta estado.
    """
    return _tools.get_account_events(phone)


@mcp.tool()
def get_chat_history(phone: str) -> dict[str, Any]:
    """Le a TRANSCRICAO da conversa do titular no WhatsApp/Omni (read-only) pelo telefone.

    Devolve as ultimas mensagens trocadas (o que foi DITO por cliente e agente/operador),
    para retomar o fio quando a sessao perdeu o contexto (pos cold-start/reset) — NAO sao
    fatos de sistema (para isso use get_account_events). Best-effort: Omni indisponivel ou
    conversa nova -> mensagens vazias; nao afirme ausencia. Nao escreve nem muta estado.
    """
    return _tools.get_chat_history(phone)


@mcp.tool()
def get_consumption_insights(phone: str) -> dict[str, Any]:
    """Insights de consumo (kWh) do titular sobre ~24 meses (read-only) pelo telefone.

    Sumariza o historico de faturas: media mensal, tendencia (subindo/estavel/caindo),
    variacao do ultimo mes vs media, pico de consumo e comparativo sazonal ano-a-ano —
    por unidade consumidora. Calculo deterministico (sem LLM), sem mutacao. Use quando o
    cliente pergunta 'por que minha conta subiu', 'quanto gastei', 'meu consumo aumentou'.
    Backend instavel -> {'encontrado': False, 'erro': 'instabilidade'} (sem stacktrace).
    """
    return _tools.get_consumption_insights(phone)


def build_app() -> Any:
    """Constroi o app ASGI (Starlette) do transporte streamable-HTTP com o
    middleware de traceId montado (R-10).

    Fronteira de observabilidade ponta-a-ponta: o `TraceIdMiddleware` le o header
    de trace da requisicao /mcp (`x-trace-id`, com fallback W3C) e o publica num
    ContextVar; o RECORDER do `AuditedCxTools` o le no momento de cada tool-call e
    grava em `tool_call_audit.trace_id` — sem tocar a assinatura de nenhuma tool.
    Import tardio do middleware mantem o modulo carregavel sem Starlette no path
    de quem so introspecta o registro de tools (ex.: teste de paridade)."""
    from src.interfaces.mcp.trace import TraceIdMiddleware

    app = mcp.streamable_http_app()
    app.add_middleware(TraceIdMiddleware)
    return app


if __name__ == "__main__":
    import uvicorn

    # R-10: subimos o app explicitamente (em vez de mcp.run) para montar o
    # TraceIdMiddleware sobre o transporte streamable-HTTP. host/port espelham o
    # FastMCP("luz-do-vale", host=..., port=...) configurado acima.
    uvicorn.run(build_app(), host=mcp.settings.host, port=mcp.settings.port)
