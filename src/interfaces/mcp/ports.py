"""Port do client da API legada (consumida pelo MCP server via REST)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class LegacyValidationError(Exception):
    """Erro de validacao do backend legado (HTTP 422)."""


class BackendUnavailableError(Exception):
    """Backend legado indisponivel/instavel (M-03): timeout, recusa de conexao,
    erro de transporte ou 5xx do servidor.

    Erro de INFRAESTRUTURA, distinto de `LegacyValidationError` (regra de
    negocio). O adapter (`HttpxLegacyApiClient`) traduz a falha bruta de rede
    nesta excecao tipada; as tools (`CxTools`) a capturam e devolvem um shape de
    erro amigavel ({'encontrado'/'ok'/'gerado': False, 'erro': 'instabilidade'})
    em vez de propagar um stacktrace cru — o agente reporta instabilidade
    temporaria sem alucinar dado ausente nem expor a stack.

    `tool` carrega o nome da tool em curso (definido em `CxTools`, nao no client)
    para correlacao/log; o `__cause__` (encadeado por `raise ... from`) preserva
    a excecao httpx original para a auditoria/depuracao."""

    def __init__(self, mensagem: str = "backend indisponivel", *, tool: str | None = None) -> None:
        super().__init__(mensagem)
        self.tool = tool


@runtime_checkable
class LegacyApiClient(Protocol):
    def find_customer(self, phone: str) -> dict[str, Any] | None: ...
    def list_contracts(self, titular_id: str) -> list[dict[str, Any]]: ...
    def list_invoices(self, uc_id: str) -> list[dict[str, Any]]: ...
    def invoice_pdf(self, fatura_id: str, presigned: bool = False) -> dict[str, Any]: ...
    def send_invoice(self, fatura_id: str) -> dict[str, Any]: ...
    def get_outage(self, bairro: str) -> dict[str, Any]: ...
    def create_ticket(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_ticket(self, protocolo: str) -> dict[str, Any] | None: ...
    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def search_kb(self, query: str) -> list[dict[str, Any]]: ...
    def get_conversation_memory(self, chat: str, limit: int = 10) -> list[dict[str, Any]]: ...
    def get_chat_messages(self, phone: str, limit: int = 10) -> list[dict[str, Any]]: ...
