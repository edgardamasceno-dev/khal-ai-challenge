"""Propagacao de `traceId` ponta-a-ponta no MCP server (R-10).

Observabilidade ponta-a-ponta (vaga Senior/Lead): correlacionar
WhatsApp<->turno<->tool-call sem mudar a assinatura de nenhuma tool. O mecanismo
e desacoplado por construcao:

1. um `ContextVar` carrega o trace_id corrente da requisicao (isolado por
   task/thread — nao vaza entre requests concorrentes);
2. um middleware Starlette montado sobre `mcp.streamable_http_app()` (ver
   `server.build_app`) le o header de entrada da requisicao `/mcp`, publica o
   valor no ContextVar e o limpa no `finally` (sem vazamento entre turnos);
3. o RECORDER de auditoria (`AuditedCxTools._wrap` -> `instrumentar(..., trace_id=
   get_trace_id())`) le o ContextVar **no momento da chamada** e grava em
   `tool_call_audit.trace_id` (coluna ja existente, ADR-0012).

Header aceito: `x-trace-id` (canonico). Fallbacks de borda, na ordem:
`x-request-id` e o `traceparent` do W3C Trace Context (extrai o trace-id de 32
hex do formato `00-<trace>-<span>-<flags>`). Ausencia de qualquer um -> geramos
um uuid4 curto, para SEMPRE haver correlacao (mesmo turno sintetico/teste).

Lado bridge/Omni: NAO implementado aqui — o omni-bridge/Genie deve repassar o
traceId do payload `omni.message` como header `x-trace-id` na chamada `/mcp`
(nota no ADR-0012). Sem isso, o middleware gera o id e a correlacao
WhatsApp<->turno fica como stretch (correlacao por chat_id+created_at).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class _HeaderLookup(Protocol):
    """Lookup minimo de headers case-insensitive (satisfeito pelo `Headers` do
    Starlette e por qualquer objeto com `.get(chave)` de um argumento)."""

    def get(self, key: str, /) -> str | None: ...


#: Header canonico de trace que o bridge/Genie deve repassar na chamada /mcp.
HEADER = "x-trace-id"
#: Fallbacks aceitos quando o header canonico esta ausente (ordem de preferencia).
HEADER_FALLBACKS: tuple[str, ...] = ("x-request-id", "traceparent")

#: ContextVar isolado por requisicao com o trace_id corrente (None fora de turno).
_trace_id: ContextVar[str | None] = ContextVar("luz_do_vale_trace_id", default=None)

#: traceparent W3C: 00-<trace-id 32hex>-<span-id 16hex>-<flags 2hex>.
_TRACEPARENT = re.compile(r"^\d{2}-([0-9a-fA-F]{32})-[0-9a-fA-F]{16}-[0-9a-fA-F]{2}$")


def set_trace_id(valor: str | None) -> Token[str | None]:
    """Publica `valor` como trace_id corrente; devolve o token para `reset`.

    O token (opaco) e usado no `finally` do middleware para restaurar o estado
    anterior do ContextVar — garante que o trace nao vaze para o proximo turno."""
    return _trace_id.set(valor)


def get_trace_id() -> str | None:
    """Le o trace_id corrente (ou None fora de uma requisicao com trace)."""
    return _trace_id.get()


def reset_trace_id(token: Token[str | None]) -> None:
    """Restaura o ContextVar ao estado anterior a `set_trace_id` (via token)."""
    _trace_id.reset(token)


def extrair_trace_id(headers: _HeaderLookup) -> str:
    """Deriva o trace_id dos headers de entrada, na ordem de preferencia.

    `x-trace-id` -> `x-request-id` -> `traceparent` (W3C, extrai os 32 hex do
    trace). Nenhum presente/valido -> uuid4 curto (12 hex) para sempre haver
    correlacao. Aceita o `Headers` do Starlette (case-insensitive) ou qualquer
    objeto com `.get(chave)`; em testes, passe um dict de chaves minusculas."""
    canonico = headers.get(HEADER)
    if canonico:
        return str(canonico)
    for chave in HEADER_FALLBACKS:
        bruto = headers.get(chave)
        if not bruto:
            continue
        if chave == "traceparent":
            m = _TRACEPARENT.match(str(bruto))
            if m:
                return m.group(1)
            continue
        return str(bruto)
    return uuid.uuid4().hex[:12]


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Captura o trace_id de cada requisicao /mcp e o publica no ContextVar.

    Ponto UNICO de captura do trace no MCP server. Le os headers, deriva o
    trace_id (com fallbacks/geracao), expoe-o pelo ContextVar durante o
    processamento do request e o limpa no `finally`. Espelha o trace_id no header
    de resposta (`x-trace-id`) para o caller correlacionar do lado de fora."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        trace_id = extrair_trace_id(request.headers)
        token = set_trace_id(trace_id)
        try:
            response = await call_next(request)
        finally:
            reset_trace_id(token)
        response.headers[HEADER] = trace_id
        return response
