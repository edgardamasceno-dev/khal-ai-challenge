"""Unit da degradacao graciosa do MCP/tools quando o backend cai (M-03).

Duas camadas, fronteira limpa:
1. ADAPTER (`HttpxLegacyApiClient`): traduz falha de INFRAESTRUTURA do backend —
   timeout, recusa de conexao, erro de transporte e 5xx — na excecao tipada
   `BackendUnavailableError`, preservando `LegacyValidationError` (422, regra de
   negocio) e o 404 (None/[] de dominio). Testado com `httpx.MockTransport`,
   sem rede real.
2. TOOLS (`CxTools`): capturam `BackendUnavailableError` e devolvem um shape de
   erro AMIGAVEL e estavel ({chave_de_falha: False, 'erro': 'instabilidade',
   'mensagem': ...}) — sem stacktrace, sem alucinar dado ausente. Cada tool usa
   a sua flag de sucesso (encontrado/ok/gerado/ha_interrupcao).

R-17 reusa este mesmo caminho de degradacao (a tool de insights tambem degrada).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.interfaces.mcp.client import HttpxLegacyApiClient
from src.interfaces.mcp.ports import (
    BackendUnavailableError,
    LegacyApiClient,
    LegacyValidationError,
)
from src.interfaces.mcp.tools import CxTools
from tests.unit.mcp_fakes import FakeLegacyApiClient

ANA = "555199990001"


def _client_com_transporte(handler: Any) -> HttpxLegacyApiClient:
    """HttpxLegacyApiClient com um MockTransport injetado (sem rede)."""
    client = HttpxLegacyApiClient("http://backend:8000")
    client._c = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend:8000")
    return client


# ----------------------------- camada ADAPTER ------------------------------ #


class TestAdapterTraduzFalhas:
    def test_timeout_vira_backend_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("read timeout", request=request)

        client = _client_com_transporte(handler)
        with pytest.raises(BackendUnavailableError):
            client.find_customer(ANA)

    def test_connect_error_vira_backend_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _client_com_transporte(handler)
        with pytest.raises(BackendUnavailableError):
            client.list_contracts("T-ANA")

    def test_5xx_vira_backend_unavailable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="service unavailable")

        client = _client_com_transporte(handler)
        with pytest.raises(BackendUnavailableError):
            client.get_outage("Centro")

    def test_backend_unavailable_encadeia_causa_original(self) -> None:
        # O __cause__ preserva a excecao httpx para depuracao/auditoria.
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        client = _client_com_transporte(handler)
        try:
            client.find_customer(ANA)
        except BackendUnavailableError as exc:
            assert isinstance(exc.__cause__, httpx.HTTPError)
        else:  # pragma: no cover - o raise acima e obrigatorio
            pytest.fail("esperava BackendUnavailableError")

    def test_422_continua_validation_error_nao_instabilidade(self) -> None:
        # 422 e regra de negocio (tipo invalido), NAO indisponibilidade.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, text="tipo invalido")

        client = _client_com_transporte(handler)
        with pytest.raises(LegacyValidationError):
            client.create_ticket({"tipo": "xpto", "idempotency_key": "k"})

    def test_404_continua_dominio_nao_instabilidade(self) -> None:
        # 404 de cliente inexistente -> None (dominio), nunca BackendUnavailableError.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        client = _client_com_transporte(handler)
        assert client.find_customer(ANA) is None


# ------------------------------ camada TOOLS ------------------------------- #


class _FakeApiCaida(FakeLegacyApiClient):
    """Backend totalmente indisponivel: toda chamada levanta BackendUnavailableError.

    Implementa o LegacyApiClient port mas simula instabilidade de infra em todos
    os metodos — o ponto de degradacao das tools (M-03)."""

    def _cai(self, *_args: Any, **_kwargs: Any) -> Any:
        raise BackendUnavailableError("backend caido (teste)")

    find_customer = _cai
    list_contracts = _cai
    list_invoices = _cai
    get_outage = _cai
    create_ticket = _cai
    get_ticket = _cai
    create_handoff = _cai
    search_kb = _cai
    send_invoice = _cai
    get_conversation_memory = _cai
    get_chat_messages = _cai


def _tools_caido() -> CxTools:
    return CxTools(_FakeApiCaida())


def _assert_shape_amigavel(resultado: dict[str, Any], chave_falha: str) -> None:
    """Toda tool degradada devolve o mesmo contrato amigavel e estavel."""
    assert resultado[chave_falha] is False
    assert resultado["erro"] == "instabilidade"
    assert isinstance(resultado["mensagem"], str) and resultado["mensagem"]
    # Sem stacktrace/detalhe tecnico vazado para o agente.
    serial = str(resultado).lower()
    assert "traceback" not in serial and "httpx" not in serial


class TestToolsDegradamGraciosamente:
    def test_find_customer_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().find_customer_by_phone(ANA), "encontrado")

    def test_list_contracts_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().list_contracts(ANA), "encontrado")

    def test_get_invoice_status_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().get_invoice_status(ANA), "encontrado")

    def test_generate_invoice_pdf_degrada_com_gerado(self) -> None:
        _assert_shape_amigavel(_tools_caido().generate_invoice_pdf(ANA), "gerado")

    def test_get_outage_degrada_com_ha_interrupcao(self) -> None:
        _assert_shape_amigavel(_tools_caido().get_outage_by_region("Centro"), "ha_interrupcao")

    def test_create_ticket_degrada_com_ok(self) -> None:
        r = _tools_caido().create_ticket(ANA, "falta_energia", "sem luz", confirmar=True)
        _assert_shape_amigavel(r, "ok")

    def test_get_ticket_status_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().get_ticket_status(ANA, "LDV1"), "encontrado")

    def test_request_human_handoff_degrada_com_ok(self) -> None:
        _assert_shape_amigavel(_tools_caido().request_human_handoff(ANA, "x"), "ok")

    def test_search_kb_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().search_knowledge_base("religacao"), "encontrado")

    def test_get_account_events_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().get_account_events(ANA), "encontrado")

    def test_get_chat_history_degrada(self) -> None:
        _assert_shape_amigavel(_tools_caido().get_chat_history(ANA), "encontrado")

    def test_get_consumption_insights_degrada(self) -> None:
        # R-17 reusa o mesmo caminho de degradacao do M-03.
        _assert_shape_amigavel(_tools_caido().get_consumption_insights(ANA), "encontrado")


def test_fake_caido_satisfaz_o_port() -> None:
    # O fake de teste continua sendo um LegacyApiClient valido (Protocol).
    assert isinstance(_FakeApiCaida(), LegacyApiClient)


def test_validation_error_nao_e_capturado_como_instabilidade() -> None:
    # M-03 so degrada indisponibilidade: um tipo invalido (422 -> LegacyValidationError)
    # continua tratado como regra de negocio pela tool ({ok: False, motivo: ...}),
    # nao como 'instabilidade'.
    r = CxTools(FakeLegacyApiClient()).create_ticket(ANA, "tipo_invalido", "x", confirmar=True)
    assert r["ok"] is False
    assert r.get("erro") != "instabilidade"
