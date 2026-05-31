"""Unit da observabilidade por tool-call MCP (T3): mascaramento de PII,
latency_ms preenchido, status (ok/denied/error), e best-effort em ambos os
sentidos (sink quebrado nao derruba a tool; erro de tool gera registro 'error'
e re-levanta intacto). Guardrails/contratos das tools permanecem inalterados.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from src.application.ports import AuditRecord, ToolCallAuditSink
from src.interfaces.mcp.audit import (
    AuditedCxTools,
    instrumentar,
    mascarar_args,
    mascarar_telefone,
)
from src.interfaces.mcp.tools import CxTools
from tests.unit.mcp_fakes import FakeLegacyApiClient

ANA = "555199990001"
CARLOS = "555199990002"
DESCONHECIDO = "550000000000"


class FakeSink(ToolCallAuditSink):
    """Sink fake que captura os registros em memoria."""

    def __init__(self) -> None:
        self.registros: list[AuditRecord] = []

    def record(self, registro: AuditRecord) -> None:
        self.registros.append(registro)


class BrokenSink(ToolCallAuditSink):
    """Sink que sempre quebra (simula falha de persistencia)."""

    def record(self, registro: AuditRecord) -> None:
        raise RuntimeError("DB indisponivel")


def _audited(sink: ToolCallAuditSink | None = None) -> AuditedCxTools:
    return AuditedCxTools(CxTools(FakeLegacyApiClient()), sink=sink)


# ---------------------------- mascaramento de PII -------------------------- #


class TestMascaramento:
    def test_telefone_vira_sufixo_de_4(self) -> None:
        assert mascarar_telefone(ANA) == "****0001"

    def test_telefone_curto_redigido(self) -> None:
        assert mascarar_telefone("12") == "***"

    def test_args_mascara_phone_e_redige_cpf(self) -> None:
        red = mascarar_args({"phone": ANA, "cpf": "52998224725", "tipo": "falta_energia"})
        assert red["phone"] == "****0001"
        assert red["cpf"] == "***"
        assert red["tipo"] == "falta_energia"  # parametro de negocio preservado

    def test_registro_nao_contem_telefone_completo_nem_cpf(self) -> None:
        sink = FakeSink()
        _audited(sink).find_customer_by_phone(ANA)
        registro = sink.registros[0]
        serializado = json.dumps(dataclasses.asdict(registro), default=str)
        assert ANA not in serializado  # telefone completo ausente
        assert "52998224725" not in serializado  # CPF ausente
        assert registro.input_redacted["phone"] == "****0001"


# ------------------------- registro por chamada ---------------------------- #


class TestRegistroPorChamada:
    def test_um_registro_por_chamada_com_campos(self) -> None:
        sink = FakeSink()
        tools = _audited(sink)
        tools.find_customer_by_phone(ANA)
        assert len(sink.registros) == 1
        r = sink.registros[0]
        assert r.tool_name == "find_customer_by_phone"
        assert r.result_status == "ok"
        assert r.latency_ms >= 0
        assert r.error_code is None

    def test_latency_preenchido_e_nao_negativo(self) -> None:
        sink = FakeSink()
        _audited(sink).get_invoice_status(ANA)
        assert sink.registros[0].latency_ms >= 0

    def test_telefone_desconhecido_status_denied(self) -> None:
        sink = FakeSink()
        _audited(sink).find_customer_by_phone(DESCONHECIDO)
        assert sink.registros[0].result_status == "denied"

    def test_create_ticket_posicional_mascara_phone(self) -> None:
        sink = FakeSink()
        _audited(sink).create_ticket(ANA, "falta_energia", "sem luz", True)
        r = sink.registros[0]
        assert r.tool_name == "create_ticket"
        assert r.input_redacted["phone"] == "****0001"
        assert r.input_redacted["tipo"] == "falta_energia"


# ----------------------- best-effort (ambos sentidos) ---------------------- #


class TestBestEffort:
    def test_sink_quebrado_nao_derruba_a_tool(self) -> None:
        # Writer quebrado: a tool retorna seu resultado normalmente, sem levantar.
        r = _audited(BrokenSink()).find_customer_by_phone(ANA)
        assert r["encontrado"] is True and r["nome"] == "Ana Souza"

    def test_sem_sink_degrada_para_apenas_log(self) -> None:
        # Sink None (nao configurado): no-op de persistencia, tool segue normal.
        r = _audited(None).get_invoice_status(ANA)
        assert r["encontrado"] is True

    def test_erro_de_tool_gera_registro_error_e_propaga(self) -> None:
        sink = FakeSink()

        def explode(phone: str) -> dict[str, Any]:
            raise ValueError("falha de negocio")

        wrapped = instrumentar(explode, tool_name="boom", sink=sink)
        with pytest.raises(ValueError, match="falha de negocio"):
            wrapped(ANA)
        # Registro 'error' produzido, com error_code, e phone mascarado.
        assert len(sink.registros) == 1
        r = sink.registros[0]
        assert r.result_status == "error"
        assert r.error_code == "ValueError"
        assert r.input_redacted["phone"] == "****0001"

    def test_erro_de_tool_com_sink_quebrado_propaga_erro_original(self) -> None:
        def explode(phone: str) -> dict[str, Any]:
            raise ValueError("erro original intacto")

        wrapped = instrumentar(explode, tool_name="boom", sink=BrokenSink())
        # O erro de negocio (nao o do sink) e o que propaga.
        with pytest.raises(ValueError, match="erro original intacto"):
            wrapped(ANA)


# ----------------------- guardrails/contratos intactos --------------------- #


class TestContratoInalterado:
    def test_retorno_identico_ao_cxtools_cru(self) -> None:
        cru = CxTools(FakeLegacyApiClient()).find_customer_by_phone(ANA)
        auditado = _audited(FakeSink()).find_customer_by_phone(ANA)
        assert auditado == cru

    def test_guardrail_de_outro_cliente_permanece(self) -> None:
        tools = _audited(FakeSink())
        protocolo = tools.create_ticket(ANA, "falta_energia", "sem luz", True)["protocolo"]
        # Carlos nao acessa chamado da Ana — guardrail intacto (auditoria observacional).
        assert tools.get_ticket_status(CARLOS, protocolo)["encontrado"] is False
