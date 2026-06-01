"""Adapter httpx do LegacyApiClient: fala REST com o backend (SPEC-001).

Degradacao graciosa (M-03): toda falha de INFRAESTRUTURA do backend — timeout,
recusa de conexao, erro de transporte ou 5xx do servidor — e traduzida aqui na
excecao tipada `BackendUnavailableError`, fronteira limpa entre o transporte
httpx (detalhe do adapter) e as tools (`CxTools`), que a convertem num shape de
erro amigavel sem stacktrace. O 422 segue como `LegacyValidationError` (regra de
negocio, nao instabilidade) e o 404 continua sendo um "nao encontrado" de
dominio (retorno None/[]), nunca indisponibilidade.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import httpx

from src.interfaces.mcp.ports import BackendUnavailableError, LegacyValidationError

#: Status HTTP do servidor que indicam INDISPONIBILIDADE (instabilidade), nao
#: regra de negocio: 5xx (erro interno/bad gateway/indisponivel/timeout upstream).
#: 4xx fica de fora — 422 e validacao, 404 e "nao encontrado" de dominio.
_STATUS_INDISPONIVEL = frozenset({500, 502, 503, 504})


def _resiliente[R](fn: Callable[..., R]) -> Callable[..., R]:
    """Envolve um metodo do adapter: traduz falha de transporte httpx (timeout,
    recusa de conexao, erro de rede) e 5xx do servidor em `BackendUnavailableError`.

    NAO captura `LegacyValidationError` (regra de negocio, levantada antes do
    `raise_for_status`) nem 404 (tratado nos metodos como None/[]). O 422 ja foi
    convertido em `LegacyValidationError` no proprio metodo e propaga intacto."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> R:
        try:
            return fn(*args, **kwargs)
        except LegacyValidationError:
            raise  # regra de negocio: nao e instabilidade.
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _STATUS_INDISPONIVEL:
                raise BackendUnavailableError(
                    f"backend respondeu {exc.response.status_code}"
                ) from exc
            raise  # 4xx inesperado: propaga (auditoria registra 'error').
        except httpx.HTTPError as exc:  # TimeoutException, ConnectError, etc.
            raise BackendUnavailableError("falha de transporte com o backend") from exc

    return wrapper


class HttpxLegacyApiClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._c = httpx.Client(base_url=base_url, timeout=timeout)

    @_resiliente
    def find_customer(self, phone: str) -> dict[str, Any] | None:
        r = self._c.get("/customers", params={"phone": phone})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def list_contracts(self, titular_id: str) -> list[dict[str, Any]]:
        r = self._c.get(f"/customers/{titular_id}/contracts")
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    @_resiliente
    def list_invoices(self, uc_id: str) -> list[dict[str, Any]]:
        r = self._c.get(f"/units/{uc_id}/invoices", params={"limit": 24})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    @_resiliente
    def invoice_pdf(self, fatura_id: str, presigned: bool = False) -> dict[str, Any]:
        r = self._c.get(f"/invoices/{fatura_id}/pdf", params={"presigned": presigned})
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def send_invoice(self, fatura_id: str) -> dict[str, Any]:
        r = self._c.post(f"/invoices/{fatura_id}/send")
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def get_outage(self, bairro: str) -> dict[str, Any]:
        r = self._c.get("/outages", params={"bairro": bairro})
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def create_ticket(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._c.post("/tickets", json=payload)
        if r.status_code == 422:
            raise LegacyValidationError(r.text)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def get_ticket(self, protocolo: str) -> dict[str, Any] | None:
        r = self._c.get(f"/tickets/{protocolo}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._c.post("/handoffs", json=payload)
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return data

    @_resiliente
    def search_kb(self, query: str) -> list[dict[str, Any]]:
        r = self._c.get("/kb/search", params={"q": query, "limit": 3})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    @_resiliente
    def get_conversation_memory(self, chat: str, limit: int = 10) -> list[dict[str, Any]]:
        """Memoria canonica do chat do titular (GET /conversations/{chat}/memory).

        `chat` e o telefone canonico normalizado (chat_id == telefone E.164, ADR-0005).
        Envia `?limit=` por cortesia ao servidor; a truncagem definitiva ocorre no
        CxTools (o router legado pode ignorar o parametro sem quebrar)."""
        r = self._c.get(f"/conversations/{chat}/memory", params={"limit": limit})
        r.raise_for_status()
        data: list[dict[str, Any]] = r.json()
        return data

    @_resiliente
    def get_chat_messages(self, phone: str, limit: int = 10) -> list[dict[str, Any]]:
        """Transcricao crua do chat do titular no WhatsApp/Omni (ADR-0013, SPEC-024).

        Reusa o transcript do operador (SPEC-018) via GET /chats/{phone}/messages,
        espelhando o consumo de `get_conversation_memory`. `phone` e o telefone canonico
        do titular (path param); o adapter Omni resolve o chatId pelas variantes do nono
        digito/LID (SPEC-015), nunca por chat citado pelo cliente. Devolve apenas a lista
        de mensagens [{id, texto, do_cliente, em}] (ordem das mais recentes), descartando
        o cursor/tem_mais de paginacao do operador. Best-effort: Omni off -> lista vazia."""
        r = self._c.get(f"/chats/{phone}/messages", params={"limit": limit})
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        mensagens: list[dict[str, Any]] = body.get("mensagens", [])
        return mensagens
