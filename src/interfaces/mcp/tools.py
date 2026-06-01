"""Logica das ferramentas MCP (use cases), com guardrails determinISticos.

Recebe um LegacyApiClient (port) -> testavel sem rede. Cada metodo corresponde
a uma ferramenta exposta ao agente. Os guardrails NAO dependem do prompt:
- acesso resolvido pelo telefone do remetente; ids nunca vem do agente;
- confirmacao antes de escrever; idempotencia por chave deterministica;
- get_ticket_status nao vaza chamado de outro cliente.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.domain.shared.phone import normalizar_msisdn, variantes_nono_digito
from src.interfaces.mcp.ports import LegacyApiClient, LegacyValidationError

# Quantidade default de eventos de sistema devolvidos ao agente (mais recentes).
# Nao e input do agente: a tool decide o teto (R-03 / SPEC-022).
_MEMORIA_LIMITE = 10

# Quantidade default de mensagens da transcricao devolvidas ao agente (mais recentes).
# Nao e input do agente: a tool decide o teto (SPEC-024 / ADR-0013).
_TRANSCRICAO_LIMITE = 10


class CxTools:
    def __init__(self, api: LegacyApiClient) -> None:
        self._api = api

    def find_customer_by_phone(self, phone: str) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao corresponde a nenhum titular."}
        return {
            "encontrado": True,
            "titular_id": titular["id"],
            "nome": titular["nome"],
            "cpf": titular["cpf_mascarado"],
            "persona": titular.get("persona_key"),
        }

    def list_contracts(self, phone: str) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        contratos = self._api.list_contracts(titular["id"])
        return {
            "encontrado": True,
            "titular": titular["nome"],
            "unidades": [
                {
                    "numero_uc": c["unidade"]["numero_uc"],
                    "bairro": c["unidade"]["bairro"],
                    "cidade": c["unidade"]["cidade"],
                    "classe": c["unidade"]["classe"],
                    "status": c["unidade"]["status"],
                }
                for c in contratos
            ],
        }

    def get_invoice_status(self, phone: str) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        abertas: list[dict[str, Any]] = []
        for c in self._api.list_contracts(titular["id"]):
            uc = c["unidade"]
            for inv in self._api.list_invoices(uc["id"]):
                if inv["status"] in ("em_aberto", "vencida"):
                    abertas.append(
                        {
                            "numero_uc": uc["numero_uc"],
                            "mes_referencia": inv["mes_referencia"],
                            "valor": inv["valor_formatado"],
                            "vencimento": inv["vencimento"],
                            "status": inv["status"],
                            "linha_digitavel": inv["linha_digitavel"],
                            "pix_copia_cola": inv["pix_copia_cola"],
                        }
                    )
        return {"encontrado": True, "titular": titular["nome"], "faturas_em_aberto": abertas}

    def generate_invoice_pdf(self, phone: str, presigned: bool = False) -> dict[str, Any]:
        """Envia a 2ª via da fatura atual ao cliente: PDF **anexo** no WhatsApp + link
        (SPEC-017 / ADR-0003). Devolve `enviado` e a URL."""
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"gerado": False, "motivo": "Telefone nao identificado."}
        faturas = [
            inv
            for c in self._api.list_contracts(titular["id"])
            for inv in self._api.list_invoices(c["unidade"]["id"])
        ]
        if not faturas:
            return {"gerado": False, "motivo": "Sem faturas para esta conta."}
        abertas = [f for f in faturas if f["status"] in ("em_aberto", "vencida")]
        alvo = max(abertas or faturas, key=lambda f: f["mes_referencia"])
        res = self._api.send_invoice(alvo["id"])
        return {
            "gerado": True,
            "enviado": res.get("enviado", False),
            "titular": titular["nome"],
            "mes_referencia": res.get("mes_referencia", alvo["mes_referencia"]),
            "status": res.get("status", alvo["status"]),
            "url": res["url"],
            "presigned": res.get("presigned"),
            "expires_at": res.get("expires_at"),
        }

    def get_outage_by_region(self, bairro: str) -> dict[str, Any]:
        res = self._api.get_outage(bairro)
        if not res["encontrada"]:
            return {"ha_interrupcao": False, "bairro": bairro}
        it = res["interrupcao"]
        return {
            "ha_interrupcao": True,
            "bairro": it["bairro"],
            "tipo": it["tipo"],
            "causa": it["causa"],
            "previsao_retorno": it["previsao_retorno"],
        }

    def create_ticket(
        self, phone: str, tipo: str, descricao: str, confirmar: bool = False
    ) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"ok": False, "motivo": "Telefone nao identificado."}
        if not confirmar:
            return {
                "ok": False,
                "needs_confirmation": True,
                "resumo": f"Abrir chamado '{tipo}' para {titular['nome']}: {descricao}",
                "instrucao": "Confirme com o cliente e chame novamente com confirmar=true.",
            }
        contratos = self._api.list_contracts(titular["id"])
        uc_id = contratos[0]["unidade"]["id"] if contratos else None
        key = "mcp-" + hashlib.sha256(f"{phone}|{tipo}|{descricao}".encode()).hexdigest()[:24]
        try:
            data = self._api.create_ticket(
                {
                    "titular_id": titular["id"],
                    "uc_id": uc_id,
                    "tipo": tipo,
                    "descricao": descricao,
                    "idempotency_key": key,
                }
            )
        except LegacyValidationError:
            return {"ok": False, "motivo": f"Tipo de chamado invalido: {tipo!r}."}
        return {
            "ok": True,
            "protocolo": data["ticket"]["protocolo"],
            "sla_horas": data["ticket"]["sla_horas"],
            "ja_existia": not data["criado_agora"],
        }

    def get_ticket_status(self, phone: str, protocolo: str) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        ticket = self._api.get_ticket(protocolo)
        if ticket is None:
            return {"encontrado": False, "motivo": "Protocolo inexistente."}
        if ticket["titular_id"] != titular["id"]:
            return {"encontrado": False, "motivo": "Protocolo nao pertence a este cliente."}
        return {
            "encontrado": True,
            "protocolo": ticket["protocolo"],
            "tipo": ticket["tipo"],
            "status": ticket["status"],
            "sla_horas": ticket["sla_horas"],
            "aberto_em": ticket["aberto_em"],
        }

    def request_human_handoff(self, phone: str, motivo: str) -> dict[str, Any]:
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"ok": False, "motivo": "Telefone nao identificado."}
        res = self._api.create_handoff(
            {
                "chamado_id": None,
                "motivo": f"[{titular['nome']}] {motivo}",
                "remetente": phone,  # LID/telefone do remetente -> pausa a IA (SPEC-016)
            }
        )
        return {"ok": True, "status": res["status"]}

    def search_knowledge_base(self, query: str) -> dict[str, Any]:
        resultados = self._api.search_kb(query)
        if not resultados:
            return {"encontrado": False, "motivo": "Nenhum artigo encontrado para a duvida."}
        return {
            "encontrado": True,
            "resultados": [
                {"slug": r["slug"], "titulo": r["titulo"], "trecho": r["trecho"]}
                for r in resultados
            ],
        }

    def get_account_events(self, phone: str) -> dict[str, Any]:
        """Le os FATOS DETERMINISTICOS DE SISTEMA da conta do titular (read-only).

        Sao eventos tipados gravados pelo ProactiveService/worker em conversation_memory
        (ADR-0005): pagamento confirmado, interrupcao aberta/encerrada, ultimo protocolo.
        NAO e a transcricao da conversa (texto cru) — para isso use get_chat_history.
        Fecha o loop proativo<->reativo (ADR-0013): o que o sistema ja resolveu/notificou
        fica legivel ao agente no abrir da conversa, para nao reoferecer 2a via de fatura
        ja paga nem reabrir chamado encerrado (R-03).

        Guardrail deterministico, identico as demais tools:
        (1) resolve o titular SEMPRE pelo `phone` do remetente (contexto confiavel do
            canal), nunca por id/telefone citado pelo cliente;
        (2) se nao resolve titular -> {"encontrado": False} e NAO consulta a memoria;
        (3) le APENAS os eventos do chat do proprio titular. A memoria e chaveada por
            chat_id == telefone E.164 (ADR-0005); a tool usa o telefone canonico
            NORMALIZADO (variantes do nono digito), nunca o telefone cru recebido.

        Somente-leitura: NAO escreve, NAO muta estado.
        """
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        itens = self._ler_eventos_do_titular(phone)
        recentes = sorted(
            itens, key=lambda m: str(m.get("atualizado_em") or ""), reverse=True
        )[:_MEMORIA_LIMITE]
        return {
            "encontrado": True,
            "titular": titular["nome"],
            "itens": [
                {
                    "chave": m["chave"],
                    "valor": m["valor"],
                    "atualizado_em": m["atualizado_em"],
                }
                for m in recentes
            ],
            "total": len(recentes),
        }

    def _ler_eventos_do_titular(self, phone: str) -> list[dict[str, Any]]:
        """Le os eventos de sistema do chat do titular pelas variantes canonicas do
        telefone (com/sem nono digito, SPEC-015), NUNCA pelo telefone cru. Para na
        primeira variante com eventos. Sem eventos -> lista vazia (best-effort)."""
        canonico = normalizar_msisdn(phone)
        for variante in variantes_nono_digito(canonico):
            itens = self._api.get_conversation_memory(variante, _MEMORIA_LIMITE)
            if itens:
                return itens
        return []

    def get_chat_history(self, phone: str) -> dict[str, Any]:
        """Le a TRANSCRICAO crua das ultimas N mensagens da conversa do titular no
        WhatsApp/Omni (texto do que foi DITO por cliente e agente/operador) — read-only.

        Recuperacao CONVERSACIONAL: complementa get_account_events (fatos de sistema)
        cobrindo 'o que ja foi conversado', util pos cold-start ou quando a sessao Genie
        reseta (janela curta/volatil) e o agente precisa retomar o fio sem repetir
        perguntas (ADR-0013 / SPEC-024). NAO sao fatos de sistema — sao mensagens.

        Guardrail deterministico, identico as demais tools:
        (1) resolve o titular/chat SEMPRE pelo `phone` do remetente (contexto confiavel
            do canal), nunca por chat citado pelo cliente;
        (2) se nao resolve titular -> {"encontrado": False} e NAO le a transcricao;
        (3) le APENAS o chat do proprio titular: o telefone canonico vai como path param
            e o adapter Omni casa o chatId pelas variantes do nono digito/LID (SPEC-015).

        Best-effort: Omni off/indisponivel -> mensagens=[] (nao quebra, nao afirma
        ausencia). Somente-leitura: NAO escreve, NAO muta estado.
        """
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        mensagens = self._api.get_chat_messages(normalizar_msisdn(phone), _TRANSCRICAO_LIMITE)
        return {
            "encontrado": True,
            "titular": titular["nome"],
            "mensagens": [
                {
                    "texto": m["texto"],
                    "do_cliente": m["do_cliente"],
                    "em": m["em"],
                }
                for m in mensagens[:_TRANSCRICAO_LIMITE]
            ],
            "total": min(len(mensagens), _TRANSCRICAO_LIMITE),
        }
