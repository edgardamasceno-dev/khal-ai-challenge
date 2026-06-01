"""Logica das ferramentas MCP (use cases), com guardrails determinISticos.

Recebe um LegacyApiClient (port) -> testavel sem rede. Cada metodo corresponde
a uma ferramenta exposta ao agente. Os guardrails NAO dependem do prompt:
- acesso resolvido pelo telefone do remetente; ids nunca vem do agente;
- confirmacao antes de escrever; idempotencia por chave deterministica;
- get_ticket_status nao vaza chamado de outro cliente.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import statistics
from collections.abc import Callable
from typing import Any

from src.domain.shared.phone import normalizar_msisdn, variantes_nono_digito
from src.interfaces.mcp.ports import (
    BackendUnavailableError,
    LegacyApiClient,
    LegacyValidationError,
)

logger = logging.getLogger("luz_do_vale.mcp.tools")

# Quantidade default de eventos de sistema devolvidos ao agente (mais recentes).
# Nao e input do agente: a tool decide o teto (R-03 / SPEC-022).
_MEMORIA_LIMITE = 10

# Quantidade default de mensagens da transcricao devolvidas ao agente (mais recentes).
# Nao e input do agente: a tool decide o teto (SPEC-024 / ADR-0013).
_TRANSCRICAO_LIMITE = 10

# Mensagem unica e amigavel de instabilidade do backend (M-03): mesma redacao em
# toda tool, sem detalhe tecnico nem stacktrace — o agente reporta a indisponibilidade
# temporaria e oferece tentar de novo, sem alucinar dado ausente.
_MSG_INSTABILIDADE = (
    "Estamos com uma instabilidade temporaria para consultar seus dados agora. "
    "Tente novamente em instantes ou peca para falar com um atendente."
)


def _degrada_se_indisponivel(
    chave_falha: str,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator de degradacao graciosa (M-03): captura `BackendUnavailableError`
    de qualquer tool e devolve um shape de erro AMIGAVEL e ESTAVEL, em vez de
    deixar o stacktrace vazar para o agente.

    `chave_falha` e a flag booleana de sucesso da tool decorada (`encontrado`,
    `ok` ou `gerado`), setada como `False` para o agente tratar como falha — e
    NUNCA confundir indisponibilidade com "dado nao existe". Acrescenta
    `erro='instabilidade'` (codigo estavel, programatico) e `mensagem` (texto
    pt-BR pronto para o cliente). A excecao original e logada (com o nome da tool),
    nao engolida silenciosamente; so nao chega ao agente como stacktrace.

    NAO captura `LegacyValidationError` nem erros de programacao — apenas a
    indisponibilidade de infra do backend (fronteira do M-03)."""

    def decorador(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            try:
                return fn(*args, **kwargs)
            except BackendUnavailableError as exc:
                logger.warning(
                    "backend indisponivel em %s (degradacao graciosa)",
                    getattr(exc, "tool", None) or fn.__name__,
                    exc_info=True,
                )
                return {
                    chave_falha: False,
                    "erro": "instabilidade",
                    "mensagem": _MSG_INSTABILIDADE,
                }

        return wrapper

    return decorador


# Banda morta (em fracao) para classificar tendencia: variacoes dentro de +-5%
# da media sao "estavel" — evita rotular ruido como subida/queda (R-17/SPEC-025).
_TENDENCIA_BANDA = 0.05
# Quantos meses recentes entram na janela de tendencia (ultimos 3 vs media global).
_JANELA_TENDENCIA = 3


def _variacao_pct(valor: int | float, base: float) -> float:
    """Variacao percentual de `valor` sobre `base`, arredondada a 1 casa.

    `base` zero (sem consumo medio) -> 0.0 (sem divisao por zero; nada a comparar)."""
    if base == 0:
        return 0.0
    return round((valor - base) / base * 100, 1)


def _classificar_tendencia(consumos: list[int], media: float) -> str:
    """Tendencia deterministica: media dos ultimos `_JANELA_TENDENCIA` meses vs a
    media global, com banda morta de +-`_TENDENCIA_BANDA`.

    > +5% -> 'subindo'; < -5% -> 'caindo'; senao 'estavel'. Serie muito curta
    (1 mes) -> 'estavel' (sem evidencia de movimento). Puro e sem LLM."""
    if len(consumos) < 2 or media == 0:
        return "estavel"
    janela = consumos[-_JANELA_TENDENCIA:]
    media_recente = statistics.mean(janela)
    desvio = (media_recente - media) / media
    if desvio > _TENDENCIA_BANDA:
        return "subindo"
    if desvio < -_TENDENCIA_BANDA:
        return "caindo"
    return "estavel"


def _comparativo_sazonal(historico: list[dict[str, Any]]) -> dict[str, Any]:
    """Comparativo ano-a-ano (YoY) do ULTIMO mes: casa o mesmo mes-calendario
    (YYYY-MM -> MM) com o ano imediatamente anterior (YYYY-1).

    Sem o mesmo mes no ano anterior (historico < 1 ano ou buraco na serie) ->
    ambos None (nao inventa comparacao). Deterministico, sem LLM."""
    ultimo = historico[-1]
    ano, mes = _ano_mes(ultimo["mes"])
    alvo = f"{ano - 1:04d}-{mes:02d}"
    por_mes = {h["mes"]: h["kwh"] for h in historico}
    anterior = por_mes.get(alvo)
    if anterior is None:
        return {"mesmo_mes_ano_anterior_kwh": None, "variacao_pct_yoy": None}
    return {
        "mesmo_mes_ano_anterior_kwh": anterior,
        "variacao_pct_yoy": _variacao_pct(ultimo["kwh"], anterior),
    }


def _ano_mes(mes_referencia: str) -> tuple[int, int]:
    """Quebra 'YYYY-MM' em (ano, mes) inteiros."""
    ano, mes = mes_referencia.split("-")
    return int(ano), int(mes)


class CxTools:
    def __init__(self, api: LegacyApiClient) -> None:
        self._api = api

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("gerado")
    def generate_invoice_pdf(
        self,
        phone: str,
        presigned: bool = False,
        mes_referencia: str | None = None,
        numero_uc: str | None = None,
    ) -> dict[str, Any]:
        """Envia a 2ª via ao cliente: PDF **anexo** no WhatsApp + link (SPEC-017 / ADR-0003).

        Sem `mes_referencia`/`numero_uc`: a fatura atual (mais recente em aberto, senão a mais
        recente). Com eles: a fatura daquela competência/UC, **QUALQUER status** (paga/vencida/em
        aberto) — SPEC-031. Em multi-UC, se a competência existir em mais de uma unidade e
        `numero_uc` não for dado, devolve `precisa_unidade` + as UCs. Devolve `gerado`, `enviado`,
        `mes_referencia`, `status` e a URL."""
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"gerado": False, "motivo": "Telefone nao identificado."}
        faturas = [
            {**inv, "numero_uc": str(c["unidade"]["numero_uc"])}
            for c in self._api.list_contracts(titular["id"])
            for inv in self._api.list_invoices(c["unidade"]["id"])
        ]
        if not faturas:
            return {"gerado": False, "motivo": "Sem faturas para esta conta."}
        if mes_referencia or numero_uc:
            cand = faturas
            if mes_referencia:
                cand = [f for f in cand if f["mes_referencia"] == mes_referencia]
            if numero_uc:
                cand = [f for f in cand if f["numero_uc"] == str(numero_uc)]
            if not cand:
                uc_txt = f" na UC {numero_uc}" if numero_uc else ""
                return {
                    "gerado": False,
                    "motivo": f"Sem fatura de {mes_referencia or 'a competência pedida'}"
                    f"{uc_txt} nesta conta.",
                }
            ucs = sorted({f["numero_uc"] for f in cand})
            if len(ucs) > 1:  # mesma competência em mais de uma UC e sem numero_uc -> desambigua
                return {
                    "gerado": False,
                    "precisa_unidade": True,
                    "unidades": ucs,
                    "motivo": "Há faturas dessa competência em mais de uma unidade; informe a UC.",
                }
            alvo = max(cand, key=lambda f: f["mes_referencia"])
        else:
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

    @_degrada_se_indisponivel("ha_interrupcao")
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

    @_degrada_se_indisponivel("ok")
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

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("ok")
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

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("encontrado")
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

        Somente-leitura: NAO escreve, NAO muta estado. Em instabilidade do backend
        (M-03), retorna {'encontrado': False, 'erro': 'instabilidade'} sem stacktrace.
        """
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        itens = self._ler_eventos_do_titular(phone)
        recentes = sorted(itens, key=lambda m: str(m.get("atualizado_em") or ""), reverse=True)[
            :_MEMORIA_LIMITE
        ]
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

    @_degrada_se_indisponivel("encontrado")
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

    @_degrada_se_indisponivel("encontrado")
    def get_consumption_insights(self, phone: str) -> dict[str, Any]:
        """Insights DETERMINISTICOS de consumo (kWh) sobre ~24 meses do titular (read-only).

        Sumariza o historico de faturas (campo `consumo_kwh` por `mes_referencia`) que ja
        chega via list_invoices — SEM endpoint REST novo, sem LLM, sem mutacao (R-17/SPEC-025).
        Por UC (espelha list_contracts): media aritmetica, tendencia (3 ultimos meses vs media,
        com banda morta de +-5%), variacao do ultimo mes vs media, pico (max consumo) e
        comparativo sazonal ano-a-ano (casa o mesmo mes calendario com o ano anterior).

        Guardrail deterministico, identico as demais tools:
        (1) resolve o titular SEMPRE pelo `phone` do remetente (contexto confiavel do canal),
            nunca por id/UC citado pelo cliente;
        (2) se nao resolve titular -> {"encontrado": False} e NAO consulta consumo;
        (3) opera APENAS sobre as UCs/faturas do proprio titular resolvido.

        Sem historico -> a UC entra com meses_analisados=0 e observacao amigavel (nunca
        stacktrace, alinhado com M-03). Somente-leitura: NAO escreve, NAO muta estado.
        """
        titular = self._api.find_customer(phone)
        if titular is None:
            return {"encontrado": False, "motivo": "Telefone nao identificado."}
        unidades = [
            self._insights_da_uc(c["unidade"]) for c in self._api.list_contracts(titular["id"])
        ]
        return {
            "encontrado": True,
            "titular": titular["nome"],
            "unidades": unidades,
            "observacao": self._observacao_geral(unidades),
        }

    def _insights_da_uc(self, unidade: dict[str, Any]) -> dict[str, Any]:
        """Calcula o bloco de insights de UMA unidade consumidora (determinIstico).

        Ordena o historico por `mes_referencia` (cronologico crescente) e deriva os
        agregados. Historico vazio -> bloco com meses_analisados=0 e observacao amigavel."""
        historico = sorted(
            (
                {"mes": inv["mes_referencia"], "kwh": int(inv["consumo_kwh"])}
                for inv in self._api.list_invoices(unidade["id"])
                if inv.get("consumo_kwh") is not None
            ),
            key=lambda h: h["mes"],
        )
        numero_uc = unidade["numero_uc"]
        if not historico:
            return {
                "numero_uc": numero_uc,
                "meses_analisados": 0,
                "media_kwh": 0.0,
                "tendencia": "estavel",
                "variacao_pct_ult_vs_media": 0.0,
                "pico": None,
                "comparativo_sazonal": {
                    "mesmo_mes_ano_anterior_kwh": None,
                    "variacao_pct_yoy": None,
                },
                "ultimo_mes": None,
                "observacao": "Sem historico de consumo para esta unidade ainda.",
            }
        consumos = [h["kwh"] for h in historico]
        media = round(statistics.mean(consumos), 1)
        ultimo = historico[-1]
        pico = max(historico, key=lambda h: h["kwh"])
        return {
            "numero_uc": numero_uc,
            "meses_analisados": len(historico),
            "media_kwh": media,
            "tendencia": _classificar_tendencia(consumos, media),
            "variacao_pct_ult_vs_media": _variacao_pct(ultimo["kwh"], media),
            "pico": {"mes_referencia": pico["mes"], "consumo_kwh": pico["kwh"]},
            "comparativo_sazonal": _comparativo_sazonal(historico),
            "ultimo_mes": {"mes_referencia": ultimo["mes"], "consumo_kwh": ultimo["kwh"]},
        }

    @staticmethod
    def _observacao_geral(unidades: list[dict[str, Any]]) -> str:
        """Observacao amigavel agregada (pt-BR), sem afirmar nada que os numeros nao digam."""
        if not unidades:
            return "Nao ha unidades consumidoras vinculadas a esta conta."
        if all(u["meses_analisados"] == 0 for u in unidades):
            return "Ainda nao ha historico de consumo suficiente para gerar insights."
        if len(unidades) == 1:
            return "Analise de consumo dos ultimos meses desta unidade."
        return f"Analise de consumo das {len(unidades)} unidades desta conta."
