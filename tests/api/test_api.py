from __future__ import annotations

import uuid
from types import SimpleNamespace

ANA_ID = "11111111-1111-1111-1111-111111111111"
UC_ID = "aaaa0001-0000-0000-0000-000000000001"
FAT_ID = "ffff0001-0000-0000-0000-000000000001"


class TestHealth:
    def test_health(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"

    def test_health_componentes(self, ctx: SimpleNamespace) -> None:
        # SPEC-014: /health agrega api + whatsapp + agente.
        comps = {c["name"]: c["status"] for c in ctx.client.get("/health").json()["components"]}
        assert comps == {"api": "ok", "whatsapp": "ok", "agente": "ok"}


class TestBillingApi:
    def test_find_customer_ok(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/customers", params={"phone": "555199990001"})
        assert r.status_code == 200
        body = r.json()
        assert body["persona_key"] == "ana.souza"
        assert "***" in body["cpf_mascarado"]

    def test_list_personas(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/personas")
        assert r.status_code == 200
        body = r.json()
        assert body[0]["nome"] == "Ana Souza"
        assert body[0]["telefone"] == "555199990001"  # em claro (atalho de busca)
        assert body[0]["persona_key"] == "ana.souza"

    def test_find_customer_desconhecido_404(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/customers", params={"phone": "559999999999"})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NotFoundError"

    def test_find_customer_nao_resolve_404(self, ctx: SimpleNamespace) -> None:
        # SPEC-015: identidade flexível — o que não resolve é 404 (não 422).
        r = ctx.client.get("/customers", params={"phone": "123"})
        assert r.status_code == 404

    def test_get_customer_e_contratos(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.get(f"/customers/{ANA_ID}").status_code == 200
        r = ctx.client.get(f"/customers/{ANA_ID}/contracts")
        assert r.status_code == 200
        assert r.json()[0]["unidade"]["bairro"] == "Jardim das Flores"

    def test_unit_e_invoices(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.get(f"/units/{UC_ID}").status_code == 200
        r = ctx.client.get(f"/units/{UC_ID}/invoices", params={"status": "em_aberto"})
        assert r.status_code == 200
        inv = r.json()[0]
        assert inv["mes_referencia"] == "2026-05" and inv["valor_formatado"].startswith("R$ ")

    def test_get_invoice_e_pdf(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.get(f"/invoices/{FAT_ID}").json()["status"] == "em_aberto"
        # PDF agora gerado/persistido (SPEC-008), não mais stub 501.
        r = ctx.client.get(f"/invoices/{FAT_ID}/pdf")
        assert r.status_code == 200
        assert r.json()["url"].endswith(f"invoices/{FAT_ID}.pdf")

    def test_patch_status_vencida_muta_e_notifica(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.patch(f"/invoices/{FAT_ID}/status", json={"status": "vencida"})
        assert r.status_code == 200 and r.json()["status"] == "vencida"
        assert ctx.client.get(f"/invoices/{FAT_ID}").json()["status"] == "vencida"
        assert "utilitycx.pagamento.vencida" in ctx.bus.published  # disparou o aviso

    def test_patch_status_em_aberto_nao_notifica(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.patch(f"/invoices/{FAT_ID}/status", json={"status": "em_aberto"})
        assert r.status_code == 200 and r.json()["status"] == "em_aberto"
        assert ctx.bus.published == []  # silencioso

    def test_patch_status_invalido_422(self, ctx: SimpleNamespace) -> None:
        # 'paga' não é editável aqui (baixa é pela aba Proativos)
        assert ctx.client.patch(
            f"/invoices/{FAT_ID}/status", json={"status": "paga"}
        ).status_code == 422

    def test_patch_status_fatura_inexistente_404(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.patch(
            f"/invoices/{uuid.uuid4()}/status", json={"status": "vencida"}
        ).status_code == 404


class TestOutageApi:
    def test_outage_encontrada(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/outages", params={"bairro": "Jardim das Flores"})
        assert r.status_code == 200 and r.json()["encontrada"] is True

    def test_outage_ausente(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/outages", params={"bairro": "Centro"})
        assert r.status_code == 200 and r.json()["encontrada"] is False


class TestTicketingApi:
    def _body(self, key: str, tipo: str = "falta_energia") -> dict[str, str]:
        return {
            "titular_id": ANA_ID, "uc_id": UC_ID, "tipo": tipo,
            "descricao": "sem luz", "idempotency_key": key,
        }

    def test_create_e_idempotencia(self, ctx: SimpleNamespace) -> None:
        r1 = ctx.client.post("/tickets", json=self._body("key-1"))
        assert r1.status_code == 201
        assert r1.json()["criado_agora"] is True
        protocolo = r1.json()["ticket"]["protocolo"]
        assert protocolo.startswith("LDV")

        r2 = ctx.client.post("/tickets", json=self._body("key-1"))
        assert r2.status_code == 200 and r2.json()["criado_agora"] is False
        assert r2.json()["ticket"]["protocolo"] == protocolo

        st = ctx.client.get(f"/tickets/{protocolo}")
        assert st.status_code == 200 and st.json()["protocolo"] == protocolo

        lst = ctx.client.get(f"/customers/{ANA_ID}/tickets")
        assert any(t["protocolo"] == protocolo for t in lst.json())

    def test_tipo_invalido_422(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.post("/tickets", json=self._body("key-2", "xpto")).status_code == 422

    def test_ticket_inexistente_404(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.get("/tickets/LDV20000101ZZZZ").status_code == 404

    def test_handoff(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.post("/handoffs", json={"motivo": "fora de escopo"})
        assert r.status_code == 201 and r.json()["status"] == "pendente"

    def test_handoff_pausa_lista_e_retoma(self, ctx: SimpleNamespace) -> None:
        # SPEC-016: POST com remetente pausa a IA; GET lista; resume retoma.
        r = ctx.client.post(
            "/handoffs", json={"motivo": "quer atendente", "remetente": "87866608713902@lid"}
        )
        hid = r.json()["id"]
        assert ctx.control.pausados == ["87866608713902@lid"]
        fila = ctx.client.get("/handoffs").json()
        assert any(h["id"] == hid for h in fila)
        resume = ctx.client.post(f"/handoffs/{hid}/resume", json={"operador": "op1"})
        assert resume.status_code == 200 and resume.json()["status"] == "resolvido"
        # retoma com o remetente normalizado (guardado no handoff)
        assert ctx.control.retomados == ["87866608713902"]
        assert ctx.client.get("/handoffs").json() == []


class TestConversationApi:
    def test_memoria_put_get_upsert(self, ctx: SimpleNamespace) -> None:
        chat = "5511999990001@s.whatsapp.net"
        r1 = ctx.client.put(f"/conversations/{chat}/memory", json={"chave": "k", "valor": {"v": 1}})
        assert r1.status_code == 200
        ctx.client.put(f"/conversations/{chat}/memory", json={"chave": "k", "valor": {"v": 2}})
        mem = ctx.client.get(f"/conversations/{chat}/memory").json()
        assert len(mem) == 1 and mem[0]["valor"] == {"v": 2}


class TestKnowledgeApi:
    def test_search_kb(self, ctx: SimpleNamespace) -> None:
        r = ctx.client.get("/kb/search", params={"q": "como transferir a titularidade"})
        assert r.status_code == 200
        body = r.json()
        assert body[0]["slug"] == "titularidade" and body[0]["trecho"]

    def test_search_sem_match(self, ctx: SimpleNamespace) -> None:
        assert ctx.client.get("/kb/search", params={"q": "zzz nada"}).json() == []
