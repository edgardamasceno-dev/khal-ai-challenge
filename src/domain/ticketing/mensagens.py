"""Mensagens determinísticas (sem LLM) do ciclo de vida do chamado, enviadas
pelo console do operador via WhatsApp (SPEC-020).

São funções puras: dado o titular e o chamado, devolvem o texto. O envio em si
fica no `TicketingService` (best-effort, via `OmniSender`).
"""

from __future__ import annotations

from src.domain.shared.value_objects import TipoChamado
from src.domain.ticketing.entities import Chamado

_TIPO_LABEL: dict[TipoChamado, str] = {
    TipoChamado.falta_energia: "falta de energia",
    TipoChamado.religacao: "religação",
    TipoChamado.segunda_via: "segunda via",
    TipoChamado.titularidade: "titularidade",
    TipoChamado.reclamacao: "reclamação",
}


def _primeiro_nome(nome: str) -> str:
    partes = nome.split()
    return partes[0] if partes else nome


def mensagem_chamado_aberto(nome: str, chamado: Chamado) -> str:
    tipo = _TIPO_LABEL.get(chamado.tipo, chamado.tipo.value)
    return (
        f"Olá, {_primeiro_nome(nome)}! Abrimos o chamado *{chamado.protocolo}* "
        f"({tipo}). Prazo de retorno: até {chamado.sla_horas}h. "
        "Você pode acompanhar por aqui. 👍"
    )


def mensagem_chamado_resolvido(nome: str, chamado: Chamado) -> str:
    return (
        f"Olá, {_primeiro_nome(nome)}! Seu chamado *{chamado.protocolo}* foi "
        "*resolvido*. ✅ Se precisar de algo mais, é só chamar."
    )
