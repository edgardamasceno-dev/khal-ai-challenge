"""Client legado fake (em memoria) que implementa o LegacyApiClient port,
imitando as respostas do backend (SPEC-001). Usado para testar as MCP tools
sem rede.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.interfaces.mcp.ports import LegacyValidationError

_TIPOS = {"falta_energia", "religacao", "segunda_via", "titularidade", "reclamacao"}
_SLA = {
    "falta_energia": 48,
    "religacao": 24,
    "segunda_via": 48,
    "titularidade": 72,
    "reclamacao": 72,
}

# Telefone -> titular
_CUSTOMERS: dict[str, dict[str, Any]] = {
    "555199990001": {
        "id": "T-ANA",
        "nome": "Ana Souza",
        "cpf_mascarado": "529.***.***-25",
        "telefone_mascarado": "5551****01",
        "email": None,
        "persona_key": "ana.souza",
    },
    "555199990002": {
        "id": "T-CARLOS",
        "nome": "Carlos Lima",
        "cpf_mascarado": "111.***.***-35",
        "telefone_mascarado": "5551****02",
        "email": None,
        "persona_key": "carlos.lima",
    },
}

_CONTRACTS: dict[str, list[dict[str, Any]]] = {
    "T-ANA": [
        {
            "id": "C-ANA",
            "modalidade": "convencional",
            "data_inicio": "2019-03-10",
            "status": "ativo",
            "unidade": {
                "id": "UC-ANA",
                "numero_uc": "100000001",
                "logradouro": "Rua das Acacias, 120",
                "bairro": "Jardim das Flores",
                "cidade": "Vale do Sol",
                "uf": "SP",
                "classe": "residencial",
                "subgrupo": "B1",
                "status": "ativa",
            },
        }
    ],
    "T-CARLOS": [
        {
            "id": "C-CARLOS",
            "modalidade": "convencional",
            "data_inicio": "2017-08-01",
            "status": "ativo",
            "unidade": {
                "id": "UC-CARLOS",
                "numero_uc": "200000001",
                "logradouro": "Av. Central, 800",
                "bairro": "Centro",
                "cidade": "Vale do Sol",
                "uf": "SP",
                "classe": "comercial",
                "subgrupo": "B3",
                "status": "ativa",
            },
        }
    ],
}


def _inv(uc: str, mes: str, status: str) -> dict[str, Any]:
    return {
        "id": f"F-{uc}-{mes}",
        "uc_id": uc,
        "mes_referencia": mes,
        "consumo_kwh": 200,
        "valor_centavos": 19000,
        "valor_formatado": "R$ 190.00",
        "bandeira": "amarela",
        "vencimento": f"{mes}-10",
        "status": status,
        "linha_digitavel": "34191.79001 ...",
        "pix_copia_cola": "00020126LUZDOVALE",
    }


_INVOICES: dict[str, list[dict[str, Any]]] = {
    "UC-ANA": [_inv("UC-ANA", "2026-05", "em_aberto"), _inv("UC-ANA", "2026-03", "paga")],
    "UC-CARLOS": [_inv("UC-CARLOS", "2026-05", "paga")],  # sem faturas em aberto
}


# chat_id (telefone canonico E.164) -> memoria proativa (ADR-0005).
# Ana tem memoria; Carlos nao. Chaves no padrao proativo.<tipo>.<subtipo>.
_MEMORY: dict[str, list[dict[str, Any]]] = {
    "555199990001": [
        {
            "chave": "proativo.outage.encerrada",
            "valor": {"texto": "Energia restabelecida no Jardim das Flores."},
            "atualizado_em": "2026-05-30T11:00:00Z",
        },
        {
            "chave": "proativo.pagamento.confirmado",
            "valor": {"texto": "Pagamento da fatura 2026-05 confirmado."},
            "atualizado_em": "2026-05-30T12:00:00Z",
        },
    ],
}


# telefone canonico -> transcricao crua do chat (SPEC-018/SPEC-024), das mais recentes.
# Ana tem conversa; Carlos nao (conversa nova -> transcricao vazia, best-effort).
_TRANSCRIPTS: dict[str, list[dict[str, Any]]] = {
    "555199990001": [
        {
            "id": "M-2",
            "texto": "Perfeito, pode seguir com a segunda via entao.",
            "do_cliente": True,
            "em": "2026-05-30T12:05:00Z",
        },
        {
            "id": "M-1",
            "texto": "Oi! Vi que sua fatura de maio esta em aberto. Posso ajudar?",
            "do_cliente": False,
            "em": "2026-05-30T12:00:00Z",
        },
    ],
}


class FakeLegacyApiClient:
    def __init__(self) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}  # protocolo -> ticket
        self._by_key: dict[str, dict[str, Any]] = {}  # idempotency_key -> ticket
        self.handoffs: list[dict[str, Any]] = []

    def find_customer(self, phone: str) -> dict[str, Any] | None:
        return _CUSTOMERS.get(phone)

    def list_contracts(self, titular_id: str) -> list[dict[str, Any]]:
        return list(_CONTRACTS.get(titular_id, []))

    def list_invoices(self, uc_id: str) -> list[dict[str, Any]]:
        return list(_INVOICES.get(uc_id, []))

    def invoice_pdf(self, fatura_id: str, presigned: bool = False) -> dict[str, Any]:
        if presigned:
            return {"url": f"http://minio/invoices/{fatura_id}.pdf?X-Expires=3600",
                    "presigned": True, "expires_at": "2026-05-30T13:00:00Z", "generated": True}
        return {"url": f"http://localhost/files/invoices/{fatura_id}.pdf",
                "presigned": False, "expires_at": None, "generated": True}

    def send_invoice(self, fatura_id: str) -> dict[str, Any]:
        return {
            "enviado": True, "mes_referencia": "2026-05", "status": "em_aberto",
            "url": f"http://minio/invoices/{fatura_id}.pdf?X-Expires=3600",
            "presigned": True, "expires_at": "2026-05-30T13:00:00Z",
        }

    def get_outage(self, bairro: str) -> dict[str, Any]:
        if bairro.lower() == "jardim das flores":
            return {
                "encontrada": True,
                "interrupcao": {
                    "id": "I-1",
                    "bairro": "Jardim das Flores",
                    "cidade": "Vale do Sol",
                    "uf": "SP",
                    "tipo": "nao_programada",
                    "causa": "Falha em equipamento de rede",
                    "inicio": "2026-05-30T10:00:00Z",
                    "previsao_retorno": "2026-05-30T15:00:00Z",
                    "status": "ativa",
                },
            }
        return {"encontrada": False, "interrupcao": None}

    def create_ticket(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["tipo"] not in _TIPOS:
            raise LegacyValidationError(f"tipo invalido: {payload['tipo']!r}")
        key = payload["idempotency_key"]
        if key in self._by_key:
            return {"criado_agora": False, "ticket": self._by_key[key]}
        protocolo = "LDV20260530" + hashlib.sha256(key.encode()).hexdigest()[:4].upper()
        ticket = {
            "id": f"TK-{len(self._tickets) + 1}",
            "protocolo": protocolo,
            "titular_id": payload["titular_id"],
            "uc_id": payload.get("uc_id"),
            "tipo": payload["tipo"],
            "descricao": payload.get("descricao"),
            "status": "aberto",
            "sla_horas": _SLA[payload["tipo"]],
            "canal": "whatsapp",
            "aberto_em": "2026-05-30T12:00:00Z",
            "atualizado_em": "2026-05-30T12:00:00Z",
        }
        self._tickets[protocolo] = ticket
        self._by_key[key] = ticket
        return {"criado_agora": True, "ticket": ticket}

    def get_ticket(self, protocolo: str) -> dict[str, Any] | None:
        return self._tickets.get(protocolo)

    def create_handoff(self, payload: dict[str, Any]) -> dict[str, Any]:
        h = {"id": f"HO-{len(self.handoffs) + 1}", "status": "pendente", **payload}
        self.handoffs.append(h)
        return h

    def get_conversation_memory(self, chat: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(_MEMORY.get(chat, []))[:limit]

    def get_chat_messages(self, phone: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(_TRANSCRIPTS.get(phone, []))[:limit]

    def search_kb(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        artigos = {
            "titularidade": {
                "slug": "titularidade",
                "titulo": "Transferencia de titularidade",
                "trecho": "Para transferir a titularidade, apresente os documentos do titular.",
            },
            "religacao": {
                "slug": "religacao",
                "titulo": "Religacao apos corte",
                "trecho": "Quite o debito; a religacao ocorre em ate 24h na area urbana.",
            },
        }
        return [a for kw, a in artigos.items() if kw in q]
