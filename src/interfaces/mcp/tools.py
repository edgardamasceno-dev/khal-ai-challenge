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

from src.interfaces.mcp.ports import LegacyApiClient, LegacyValidationError


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
        """Gera (ou reaproveita) o PDF da fatura atual do titular e devolve a URL."""
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
        doc = self._api.invoice_pdf(alvo["id"], presigned)
        return {
            "gerado": True,
            "titular": titular["nome"],
            "mes_referencia": alvo["mes_referencia"],
            "status": alvo["status"],
            "url": doc["url"],
            "presigned": doc["presigned"],
            "expires_at": doc.get("expires_at"),
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
