"""Observabilidade por tool-call MCP (T3): mascaramento de PII, RECORDER de
instrumentacao e log estruturado. Best-effort por construcao.

O RECORDER envolve cada metodo de `CxTools` sem mudar assinatura nem retorno:
mede latencia, deriva o `result_status` ('ok'|'error'|'denied'), monta o
`AuditRecord` com o input **mascarado** e:

1. emite um log estruturado (JSON) por chamada (sem PII em claro); e
2. grava no `ToolCallAuditSink` de forma **best-effort** — qualquer excecao do
   sink e logada e engolida, NUNCA derruba a tool nem altera seu retorno.

Se a tool levantar, o erro original e **propagado intacto** e ainda assim um
registro com result_status='error' + error_code e produzido (a auditoria nao
engole nem mascara o erro de negocio).
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from src.application.ports import AuditRecord, ToolCallAuditSink
from src.interfaces.mcp.tools import CxTools
from src.interfaces.mcp.trace import get_trace_id

logger = logging.getLogger("luz_do_vale.mcp.audit")

# Chaves de argumento tratadas como telefone (mascaradas para sufixo de 4 digitos).
_CHAVES_TELEFONE = frozenset({"phone", "telefone", "remetente", "msisdn"})
# Chaves de argumento sensiveis nunca gravadas em claro (CPF, etc.).
_CHAVES_SENSIVEIS = frozenset({"cpf", "documento", "doc"})
_NAO_DIGITO = re.compile(r"\D")
_REDIGIDO = "***"


def mascarar_telefone(valor: str) -> str:
    """Telefone -> sufixo dos ultimos 4 digitos (ex.: '****0001'). Nunca o numero
    completo. Se houver menos de 4 digitos, mascara tudo (`***`)."""
    digitos = _NAO_DIGITO.sub("", valor)
    if len(digitos) < 4:
        return _REDIGIDO
    return f"****{digitos[-4:]}"


def mascarar_args(args: dict[str, Any]) -> dict[str, Any]:
    """Aplica mascaramento de PII a um dicionario de argumentos de tool.

    - chaves de telefone -> sufixo de 4 digitos (nunca o numero inteiro);
    - chaves sensiveis (cpf/documento) -> redigidas (`***`), nunca em claro;
    - demais valores preservados (sao parametros de negocio, nao PII).
    """
    redigido: dict[str, Any] = {}
    for chave, valor in args.items():
        chave_norm = chave.lower()
        if chave_norm in _CHAVES_SENSIVEIS:
            redigido[chave] = _REDIGIDO
        elif chave_norm in _CHAVES_TELEFONE and isinstance(valor, str):
            redigido[chave] = mascarar_telefone(valor)
        else:
            redigido[chave] = valor
    return redigido


def _status_do_resultado(resultado: Any) -> str:
    """Deriva o status de uma chamada bem-sucedida (sem excecao).

    Um guardrail/negacao determinIstica das tools sinaliza falha logica via
    `encontrado=False`, `ok=False` ou `gerado=False` -> 'denied'. Caso contrario,
    'ok'. (Puramente observacional: nao altera o retorno da tool.)
    """
    if isinstance(resultado, dict):
        for chave in ("encontrado", "ok", "gerado"):
            if resultado.get(chave) is False:
                return "denied"
    return "ok"


def _emitir_log(record: AuditRecord) -> None:
    """Log estruturado (JSON) por chamada — sem PII em claro (input ja mascarado)."""
    payload = {
        "evento": "tool_call",
        "tool_name": record.tool_name,
        "result_status": record.result_status,
        "latency_ms": record.latency_ms,
        "error_code": record.error_code,
        "trace_id": record.trace_id,
        "chat_id": record.chat_id,
        "input_redacted": record.input_redacted,
    }
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


def _persistir_best_effort(sink: ToolCallAuditSink | None, record: AuditRecord) -> None:
    """Grava no sink de forma best-effort. Sem sink configurado -> no-op
    (degrada para apenas-log). Qualquer falha do sink e logada e engolida."""
    if sink is None:
        return
    try:
        sink.record(record)
    except Exception:  # noqa: BLE001 — auditoria NUNCA derruba a tool.
        logger.warning("falha ao persistir tool_call_audit (engolida)", exc_info=True)


def instrumentar[R](
    fn: Callable[..., R],
    *,
    tool_name: str,
    sink: ToolCallAuditSink | None,
    trace_id: str | None = None,
    chat_id: str | None = None,
) -> Callable[..., R]:
    """Envolve uma callable de tool, preservando assinatura e retorno.

    Mede `latency_ms` na propria chamada, deriva `result_status`/`error_code`,
    mascara os argumentos e produz log + persistencia best-effort. Em caso de
    excecao, registra 'error' e **re-levanta o erro original**.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> R:
        inicio = time.perf_counter()
        nomeados = _nomear_args(fn, args, kwargs)
        try:
            resultado = fn(*args, **kwargs)
        except Exception as exc:
            latency_ms = max(0, round((time.perf_counter() - inicio) * 1000))
            record = AuditRecord(
                tool_name=tool_name,
                result_status="error",
                latency_ms=latency_ms,
                input_redacted=mascarar_args(nomeados),
                error_code=type(exc).__name__,
                trace_id=trace_id,
                chat_id=chat_id,
            )
            _emitir_log(record)
            _persistir_best_effort(sink, record)
            raise  # erro original propagado intacto.
        latency_ms = max(0, round((time.perf_counter() - inicio) * 1000))
        record = AuditRecord(
            tool_name=tool_name,
            result_status=_status_do_resultado(resultado),
            latency_ms=latency_ms,
            input_redacted=mascarar_args(nomeados),
            error_code=None,
            trace_id=trace_id,
            chat_id=chat_id,
        )
        _emitir_log(record)
        _persistir_best_effort(sink, record)
        return resultado

    return wrapper


def _nomear_args(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Liga args posicionais aos nomes de parametro (ignora `self`), uniao com kwargs.

    Permite mascarar por nome de chave (ex.: 'phone') de forma robusta a chamadas
    posicionais ou nomeadas. Desembrulha (`inspect.unwrap`) a tool decorada — ex.:
    o `_degrada_se_indisponivel` (M-03) embrulha o metodo com `functools.wraps`, e
    sem o unwrap leriamos `(*args, **kwargs)` do wrapper em vez de `(self, phone)`."""
    alvo = inspect.unwrap(fn)
    nomes = list(alvo.__code__.co_varnames[: alvo.__code__.co_argcount])
    if nomes and nomes[0] == "self":
        nomes = nomes[1:]
    nomeados: dict[str, Any] = dict(zip(nomes, args, strict=False))
    nomeados.update(kwargs)
    return nomeados


class AuditedCxTools:
    """Decorator de `CxTools` que instrumenta os 12 metodos-tool (T3) sem mudar
    assinatura nem retorno. Cada chamada gera UM `AuditRecord` (log + sink
    best-effort). Guardrails e contratos das tools permanecem intactos.

    Espelha a superficie publica de `CxTools` — `server.py` apenas troca a
    instancia, sem tocar nas `@mcp.tool()`. Delegacao tipada (mypy strict).
    """

    def __init__(self, tools: CxTools, sink: ToolCallAuditSink | None = None) -> None:
        self._tools = tools
        self._sink = sink

    def _wrap(
        self, metodo: Callable[..., dict[str, Any]], nome: str
    ) -> Callable[..., dict[str, Any]]:
        # Leitura TARDIA do trace_id (R-10): `_wrap` roda a cada chamada de tool,
        # entao `get_trace_id()` ja captura o trace do request corrente, publicado
        # pelo TraceIdMiddleware no ContextVar. None fora de um request com trace
        # (ex.: chamada direta em teste) — a auditoria grava trace_id NULL, sem
        # quebrar. Nao muda a assinatura de nenhuma @mcp.tool nem do CxTools.
        return instrumentar(metodo, tool_name=nome, sink=self._sink, trace_id=get_trace_id())

    def find_customer_by_phone(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.find_customer_by_phone, "find_customer_by_phone")(phone)

    def list_contracts(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.list_contracts, "list_contracts")(phone)

    def get_invoice_status(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_invoice_status, "get_invoice_status")(phone)

    def generate_invoice_pdf(self, phone: str, presigned: bool = False) -> dict[str, Any]:
        return self._wrap(self._tools.generate_invoice_pdf, "generate_invoice_pdf")(
            phone, presigned
        )

    def get_outage_by_region(self, bairro: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_outage_by_region, "get_outage_by_region")(bairro)

    def create_ticket(
        self, phone: str, tipo: str, descricao: str, confirmar: bool = False
    ) -> dict[str, Any]:
        return self._wrap(self._tools.create_ticket, "create_ticket")(
            phone, tipo, descricao, confirmar
        )

    def get_ticket_status(self, phone: str, protocolo: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_ticket_status, "get_ticket_status")(phone, protocolo)

    def request_human_handoff(self, phone: str, motivo: str) -> dict[str, Any]:
        return self._wrap(self._tools.request_human_handoff, "request_human_handoff")(phone, motivo)

    def search_knowledge_base(self, query: str) -> dict[str, Any]:
        return self._wrap(self._tools.search_knowledge_base, "search_knowledge_base")(query)

    def get_account_events(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_account_events, "get_account_events")(phone)

    def get_chat_history(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_chat_history, "get_chat_history")(phone)

    def get_consumption_insights(self, phone: str) -> dict[str, Any]:
        return self._wrap(self._tools.get_consumption_insights, "get_consumption_insights")(phone)
