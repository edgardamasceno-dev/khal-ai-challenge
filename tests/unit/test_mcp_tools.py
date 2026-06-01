from __future__ import annotations

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


class TestSearchKnowledgeBase:
    def test_com_match_cita_slug(self) -> None:
        r = _tools().search_knowledge_base("como transferir a titularidade")
        assert r["encontrado"] is True
        assert r["resultados"][0]["slug"] == "titularidade"
        assert r["resultados"][0]["trecho"]

    def test_sem_match(self) -> None:
        out = _tools().search_knowledge_base("assunto totalmente inexistente zzz")
        assert out["encontrado"] is False


class TestGenerateInvoicePdf:
    def test_envia_2a_via_como_anexo(self) -> None:
        # SPEC-017: a tool envia o anexo e reporta enviado + url.
        r = _tools().generate_invoice_pdf(ANA)
        assert r["gerado"] is True and r["enviado"] is True
        assert r["titular"] and r["url"]

    def test_telefone_desconhecido(self) -> None:
        r = _tools().generate_invoice_pdf(DESCONHECIDO)
        assert r["gerado"] is False


class TestConversationContext:
    """get_conversation_context (R-03 / SPEC-022): memoria read-only do titular."""

    def test_retorna_contexto_do_titular(self) -> None:
        r = _tools().get_conversation_context(ANA)
        assert r["encontrado"] is True and r["titular"] == "Ana Souza"
        chaves = {item["chave"] for item in r["itens"]}
        assert "proativo.pagamento.confirmado" in chaves
        assert r["total"] == len(r["itens"]) >= 1

    def test_itens_do_mais_recente_para_o_mais_antigo(self) -> None:
        # A memoria mais recente (atualizado_em maior) vem primeiro.
        itens = _tools().get_conversation_context(ANA)["itens"]
        ts = [item["atualizado_em"] for item in itens]
        assert ts == sorted(ts, reverse=True)
        assert itens[0]["chave"] == "proativo.pagamento.confirmado"

    def test_telefone_desconhecido_nao_consulta_memoria(self) -> None:
        # Guardrail: telefone sem titular -> encontrado=False e nao expoe memoria.
        r = _tools().get_conversation_context(DESCONHECIDO)
        assert r["encontrado"] is False
        assert "itens" not in r

    def test_nao_vaza_memoria_de_outro_titular(self) -> None:
        # Carlos (titular valido, sem memoria) nao recebe a memoria da Ana.
        r = _tools().get_conversation_context(CARLOS)
        assert r["encontrado"] is True and r["titular"] == "Carlos Lima"
        assert r["itens"] == [] and r["total"] == 0

    def test_best_effort_sem_memoria(self) -> None:
        # Titular sem nenhuma memoria gravada -> itens vazios, sem quebrar.
        r = _tools().get_conversation_context(CARLOS)
        assert r["encontrado"] is True and r["itens"] == []
