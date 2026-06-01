from __future__ import annotations

from typing import Any

from src.interfaces.mcp.tools import CxTools
from tests.unit.mcp_fakes import FakeLegacyApiClient, _inv

ANA = "555199990001"
CARLOS = "555199990002"
DESCONHECIDO = "550000000000"
MULTI = "555100000099"


class _FakeMultiUC(FakeLegacyApiClient):
    """Titular com 2 UCs e faturas no MESMO mês — p/ testar a desambiguação (SPEC-031)."""

    def find_customer(self, phone: str) -> dict[str, Any] | None:
        if phone == MULTI:
            return {"id": "T-MULTI", "nome": "Multi UC"}
        return super().find_customer(phone)

    def list_contracts(self, titular_id: str) -> list[dict[str, Any]]:
        if titular_id == "T-MULTI":
            return [
                {"unidade": {"id": "UC-M1", "numero_uc": "900000001"}},
                {"unidade": {"id": "UC-M2", "numero_uc": "900000002"}},
            ]
        return super().list_contracts(titular_id)

    def list_invoices(self, uc_id: str) -> list[dict[str, Any]]:
        if uc_id == "UC-M1":
            return [_inv("UC-M1", "2026-05", "paga")]
        if uc_id == "UC-M2":
            return [_inv("UC-M2", "2026-05", "em_aberto")]
        return super().list_invoices(uc_id)

    def send_invoice(self, fatura_id: str) -> dict[str, Any]:
        # ecoa o status pela UC do id (F-UC-M1-... = paga; F-UC-M2-... = em_aberto).
        status = "paga" if "UC-M1" in fatura_id else "em_aberto"
        return {"enviado": True, "mes_referencia": "2026-05", "status": status, "url": "http://x"}


def _tools() -> CxTools:
    return CxTools(FakeLegacyApiClient())


class _FakeApiSemOmni(FakeLegacyApiClient):
    """Variante do fake com o Omni indisponivel: a transcricao sempre vem vazia
    (best-effort) — o adapter Omni real engole a falha e devolve []. O resto da
    API legada continua respondendo (titular resolve normalmente)."""

    def get_chat_messages(self, phone: str, limit: int = 10) -> list[dict[str, Any]]:
        return []


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

    def test_mes_referencia_gera_fatura_paga(self) -> None:
        # SPEC-031: com mes_referencia, gera o PDF daquela fatura — QUALQUER status.
        r = _tools().generate_invoice_pdf(ANA, mes_referencia="2026-04")
        assert r["gerado"] is True
        assert r["mes_referencia"] == "2026-04" and r["status"] == "paga"

    def test_default_sem_filtro_pega_em_aberto(self) -> None:
        # Regressão SPEC-031: sem filtro segue na mais recente em aberto.
        r = _tools().generate_invoice_pdf(ANA)
        assert r["mes_referencia"] == "2026-05" and r["status"] == "em_aberto"

    def test_mes_inexistente_nao_gera(self) -> None:
        r = _tools().generate_invoice_pdf(ANA, mes_referencia="1990-01")
        assert r["gerado"] is False and "motivo" in r

    def test_numero_uc_errada_nao_gera(self) -> None:
        r = _tools().generate_invoice_pdf(ANA, numero_uc="999999999")
        assert r["gerado"] is False

    def test_mes_e_uc_precisos(self) -> None:
        r = _tools().generate_invoice_pdf(ANA, mes_referencia="2026-04", numero_uc="100000001")
        assert r["gerado"] is True and r["status"] == "paga"


class TestGenerateInvoicePdfMultiUC:
    def _t(self) -> CxTools:
        return CxTools(_FakeMultiUC())

    def test_mes_em_duas_ucs_pede_unidade(self) -> None:
        # SPEC-031: mês em 2 UCs e sem numero_uc -> desambigua (precisa_unidade).
        r = self._t().generate_invoice_pdf(MULTI, mes_referencia="2026-05")
        assert r["gerado"] is False and r.get("precisa_unidade") is True
        assert set(r["unidades"]) == {"900000001", "900000002"}

    def test_mes_mais_uc_resolve(self) -> None:
        r = self._t().generate_invoice_pdf(MULTI, mes_referencia="2026-05", numero_uc="900000001")
        assert r["gerado"] is True and r["status"] == "paga"


class TestAccountEvents:
    """get_account_events (ex get_conversation_context, R-03 / SPEC-022):
    eventos deterministicos de sistema da conta, read-only, do proprio titular."""

    def test_retorna_eventos_do_titular(self) -> None:
        r = _tools().get_account_events(ANA)
        assert r["encontrado"] is True and r["titular"] == "Ana Souza"
        chaves = {item["chave"] for item in r["itens"]}
        assert "proativo.pagamento.confirmado" in chaves
        assert r["total"] == len(r["itens"]) >= 1

    def test_itens_do_mais_recente_para_o_mais_antigo(self) -> None:
        # O evento mais recente (atualizado_em maior) vem primeiro.
        itens = _tools().get_account_events(ANA)["itens"]
        ts = [item["atualizado_em"] for item in itens]
        assert ts == sorted(ts, reverse=True)
        assert itens[0]["chave"] == "proativo.pagamento.confirmado"

    def test_telefone_desconhecido_nao_consulta_memoria(self) -> None:
        # Guardrail: telefone sem titular -> encontrado=False e nao expoe eventos.
        r = _tools().get_account_events(DESCONHECIDO)
        assert r["encontrado"] is False
        assert "itens" not in r

    def test_nao_vaza_eventos_de_outro_titular(self) -> None:
        # Carlos (titular valido, sem eventos) nao recebe os eventos da Ana.
        r = _tools().get_account_events(CARLOS)
        assert r["encontrado"] is True and r["titular"] == "Carlos Lima"
        assert r["itens"] == [] and r["total"] == 0

    def test_best_effort_sem_eventos(self) -> None:
        # Titular sem nenhum evento gravado -> itens vazios, sem quebrar.
        r = _tools().get_account_events(CARLOS)
        assert r["encontrado"] is True and r["itens"] == []


class TestChatHistory:
    """get_chat_history (SPEC-024 / ADR-0013): transcricao conversacional read-only
    do chat do proprio titular (reuso do transcript do operador, SPEC-018)."""

    def test_retorna_transcricao_do_titular(self) -> None:
        r = _tools().get_chat_history(ANA)
        assert r["encontrado"] is True and r["titular"] == "Ana Souza"
        textos = [m["texto"] for m in r["mensagens"]]
        assert any("segunda via" in t for t in textos)
        assert r["total"] == len(r["mensagens"]) >= 1

    def test_mensagens_marcam_origem_cliente_vs_agente(self) -> None:
        # do_cliente=True = recebida do cliente; False = enviada pelo agente/operador.
        mensagens = _tools().get_chat_history(ANA)["mensagens"]
        assert any(m["do_cliente"] is True for m in mensagens)
        assert any(m["do_cliente"] is False for m in mensagens)

    def test_telefone_desconhecido_nao_le_transcricao(self) -> None:
        # Guardrail: telefone sem titular -> encontrado=False e nao expoe transcricao.
        r = _tools().get_chat_history(DESCONHECIDO)
        assert r["encontrado"] is False
        assert "mensagens" not in r

    def test_nao_vaza_transcricao_de_outro_titular(self) -> None:
        # Carlos (titular valido, conversa nova) nao recebe a transcricao da Ana.
        r = _tools().get_chat_history(CARLOS)
        assert r["encontrado"] is True and r["titular"] == "Carlos Lima"
        assert r["mensagens"] == [] and r["total"] == 0

    def test_best_effort_omni_indisponivel(self) -> None:
        # Omni off/indisponivel (get_chat_messages -> []) -> mensagens vazias, sem quebrar
        # e sem afirmar ausencia (encontrado segue True para o titular resolvido).
        tools = CxTools(_FakeApiSemOmni())
        r = tools.get_chat_history(ANA)
        assert r["encontrado"] is True and r["titular"] == "Ana Souza"
        assert r["mensagens"] == [] and r["total"] == 0
