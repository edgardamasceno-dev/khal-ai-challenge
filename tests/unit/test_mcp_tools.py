from __future__ import annotations

import pytest

from src.interfaces.mcp.tools import CxTools
from tests.unit.mcp_fakes import FakeLegacyApiClient

ANA = "555199990001"
CARLOS = "555199990002"
DESCONHECIDO = "550000000000"


def _tools() -> CxTools:
    return CxTools(FakeLegacyApiClient())


class TestFindCustomer:
    def test_conhecido(self) -> None:
        r = _tools().find_customer_by_phone(ANA)
        assert r["encontrado"] is True and r["nome"] == "Ana Souza"

    def test_desconhecido(self) -> None:
        assert _tools().find_customer_by_phone(DESCONHECIDO)["encontrado"] is False


class TestListContracts:
    def test_conhecido(self) -> None:
        r = _tools().list_contracts(ANA)
        assert r["encontrado"] is True
        assert any(u["bairro"] == "Jardim das Flores" for u in r["unidades"])

    def test_telefone_desconhecido(self) -> None:
        assert _tools().list_contracts(DESCONHECIDO)["encontrado"] is False


class TestInvoiceStatus:
    def test_com_faturas_em_aberto(self) -> None:
        r = _tools().get_invoice_status(ANA)
        assert r["encontrado"] is True and len(r["faturas_em_aberto"]) >= 1

    def test_sem_faturas_em_aberto(self) -> None:
        r = _tools().get_invoice_status(CARLOS)
        assert r["encontrado"] is True and r["faturas_em_aberto"] == []

    def test_telefone_desconhecido(self) -> None:
        assert _tools().get_invoice_status(DESCONHECIDO)["encontrado"] is False


class TestOutage:
    def test_ativa(self) -> None:
        r = _tools().get_outage_by_region("Jardim das Flores")
        assert r["ha_interrupcao"] is True and r["tipo"] == "nao_programada"

    def test_ausente(self) -> None:
        assert _tools().get_outage_by_region("Centro")["ha_interrupcao"] is False


class TestCreateTicket:
    def test_sem_confirmar(self) -> None:
        r = _tools().create_ticket(ANA, "falta_energia", "sem luz", confirmar=False)
        assert r["ok"] is False and r["needs_confirmation"] is True

    def test_confirmado(self) -> None:
        r = _tools().create_ticket(ANA, "falta_energia", "sem luz", confirmar=True)
        assert r["ok"] is True and r["protocolo"].startswith("LDV") and r["sla_horas"] == 48

    def test_idempotente(self) -> None:
        tools = _tools()
        a = tools.create_ticket(ANA, "falta_energia", "sem luz", confirmar=True)
        b = tools.create_ticket(ANA, "falta_energia", "sem luz", confirmar=True)
        assert b["ja_existia"] is True and b["protocolo"] == a["protocolo"]

    def test_tipo_invalido(self) -> None:
        r = _tools().create_ticket(ANA, "xpto", "x", confirmar=True)
        assert r["ok"] is False

    def test_telefone_desconhecido(self) -> None:
        r = _tools().create_ticket(DESCONHECIDO, "falta_energia", "x", confirmar=True)
        assert r["ok"] is False


class TestTicketStatus:
    def _abre(self, tools: CxTools) -> str:
        return tools.create_ticket(ANA, "falta_energia", "sem luz", confirmar=True)["protocolo"]

    def test_do_titular(self) -> None:
        tools = _tools()
        protocolo = self._abre(tools)
        r = tools.get_ticket_status(ANA, protocolo)
        assert r["encontrado"] is True and r["protocolo"] == protocolo

    def test_inexistente(self) -> None:
        assert _tools().get_ticket_status(ANA, "LDV20000101ZZZZ")["encontrado"] is False

    def test_de_outro_cliente_negado(self) -> None:
        tools = _tools()
        protocolo = self._abre(tools)  # chamado da Ana
        r = tools.get_ticket_status(CARLOS, protocolo)  # Carlos tenta acessar
        assert r["encontrado"] is False


class TestHandoff:
    def test_ok(self) -> None:
        r = _tools().request_human_handoff(ANA, "fora de escopo")
        assert r["ok"] is True and r["status"] == "pendente"

    def test_telefone_desconhecido(self) -> None:
        assert _tools().request_human_handoff(DESCONHECIDO, "x")["ok"] is False
