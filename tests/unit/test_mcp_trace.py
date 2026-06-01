"""Unit do traceId ponta-a-ponta no MCP server (R-10), conforme r10_design.

Cobre as duas pontas, deterministico e sem rede real:
1. ContextVar + extracao + middleware: o `TraceIdMiddleware` le o header de
   entrada (`x-trace-id`, com fallbacks `x-request-id`/`traceparent` W3C),
   publica no ContextVar durante o request e o limpa no `finally`; ausencia ->
   uuid gerado. Testado via app Starlette minima com ASGITransport.
2. Ligacao ao audit: com o trace setado no ContextVar, o `AuditedCxTools` grava
   `AuditRecord.trace_id == valor` (capturado por um FakeSink); sem trace ->
   trace_id None. Prova que cada tool-call grava o trace corrente sem mudar a
   assinatura de nenhuma tool.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from src.application.ports import AuditRecord, ToolCallAuditSink
from src.interfaces.mcp.audit import AuditedCxTools
from src.interfaces.mcp.tools import CxTools
from src.interfaces.mcp.trace import (
    HEADER,
    TraceIdMiddleware,
    extrair_trace_id,
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)
from tests.unit.mcp_fakes import FakeLegacyApiClient

ANA = "555199990001"


class FakeSink(ToolCallAuditSink):
    def __init__(self) -> None:
        self.registros: list[AuditRecord] = []

    def record(self, registro: AuditRecord) -> None:
        self.registros.append(registro)


# --------------------------- extracao do header ---------------------------- #


class TestExtrairTraceId:
    def test_header_canonico(self) -> None:
        assert extrair_trace_id({"x-trace-id": "abc-123"}) == "abc-123"

    def test_fallback_x_request_id(self) -> None:
        assert extrair_trace_id({"x-request-id": "req-9"}) == "req-9"

    def test_fallback_traceparent_w3c(self) -> None:
        # traceparent: 00-<32hex trace>-<16hex span>-<2hex flags> -> extrai o trace.
        tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        assert extrair_trace_id({"traceparent": tp}) == "4bf92f3577b34da6a3ce929d0e0e4736"

    def test_traceparent_malformado_cai_para_gerado(self) -> None:
        out = extrair_trace_id({"traceparent": "nao-e-traceparent"})
        assert out and out != "nao-e-traceparent"

    def test_preferencia_canonico_sobre_fallbacks(self) -> None:
        headers = {"x-trace-id": "canon", "x-request-id": "fb"}
        assert extrair_trace_id(headers) == "canon"

    def test_ausencia_gera_id(self) -> None:
        # Sem header nenhum -> sempre ha correlacao (uuid curto), nunca vazio/None.
        out = extrair_trace_id({})
        assert isinstance(out, str) and len(out) >= 8


# ------------------------------- ContextVar -------------------------------- #


class TestContextVar:
    def test_set_get_reset(self) -> None:
        assert get_trace_id() is None
        token = set_trace_id("xyz")
        try:
            assert get_trace_id() == "xyz"
        finally:
            reset_trace_id(token)
        assert get_trace_id() is None


# ------------------------------- middleware -------------------------------- #


def _app_capturando() -> Starlette:
    """App Starlette minima com o TraceIdMiddleware: o endpoint le o trace_id
    corrente do ContextVar (dentro do request) e o devolve no corpo."""

    async def endpoint(request: Request) -> Response:
        return JSONResponse({"trace_visto": get_trace_id()})

    app = Starlette(routes=[Route("/mcp", endpoint)])
    app.add_middleware(TraceIdMiddleware)
    return app


async def _get(app: Starlette, headers: dict[str, str] | None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/mcp", headers=headers or {})


class TestMiddleware:
    def test_header_disponivel_no_handler(self) -> None:
        resp = asyncio.run(_get(_app_capturando(), {HEADER: "trace-do-request"}))
        assert resp.status_code == 200
        assert resp.json()["trace_visto"] == "trace-do-request"
        # Espelhado no header de resposta para o caller correlacionar.
        assert resp.headers[HEADER] == "trace-do-request"

    def test_sem_header_gera_trace(self) -> None:
        resp = asyncio.run(_get(_app_capturando(), None))
        visto = resp.json()["trace_visto"]
        assert visto and visto == resp.headers[HEADER]

    def test_contextvar_limpo_apos_request(self) -> None:
        asyncio.run(_get(_app_capturando(), {HEADER: "efemero"}))
        # O middleware reseta no finally: nada vaza para fora do request.
        assert get_trace_id() is None


# --------------------------- ligacao ao audit ------------------------------ #


def _audited(sink: ToolCallAuditSink) -> AuditedCxTools:
    return AuditedCxTools(CxTools(FakeLegacyApiClient()), sink=sink)


class TestLigacaoAudit:
    def test_tool_call_grava_trace_corrente(self) -> None:
        sink = FakeSink()
        token = set_trace_id("trace-da-vez")
        try:
            _audited(sink).find_customer_by_phone(ANA)
        finally:
            reset_trace_id(token)
        assert sink.registros[0].trace_id == "trace-da-vez"

    def test_sem_trace_grava_none(self) -> None:
        sink = FakeSink()
        # Fora de qualquer request/trace: a auditoria grava trace_id None, sem quebrar.
        _audited(sink).find_customer_by_phone(ANA)
        assert sink.registros[0].trace_id is None

    def test_leitura_tardia_por_tool_call(self) -> None:
        # Cada tool-call captura o trace vigente NO MOMENTO da chamada (leitura tardia).
        sink = FakeSink()
        tools = _audited(sink)
        t1 = set_trace_id("t-1")
        try:
            tools.find_customer_by_phone(ANA)
        finally:
            reset_trace_id(t1)
        t2 = set_trace_id("t-2")
        try:
            tools.get_invoice_status(ANA)
        finally:
            reset_trace_id(t2)
        assert sink.registros[0].trace_id == "t-1"
        assert sink.registros[1].trace_id == "t-2"


@pytest.fixture(autouse=True)
def _trace_limpo() -> object:
    # Garante que nenhum teste vaze trace para o proximo (isolamento do ContextVar).
    token = set_trace_id(None)
    yield
    reset_trace_id(token)
