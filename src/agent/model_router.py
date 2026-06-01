"""Roteador de modelo determinístico por caso (R-09 / ADR-0014, pilar 3).

Heurística **pura** (sem I/O, sem hop de LLM) que mapeia a mensagem do cliente em
um tier de modelo, materializando a política do ADR-0014:

- ``SONNET`` = default seguro (transacional: fatura, outage, ticket, 2ª via);
- ``HAIKU`` = saudação / FAQ curta de KB (barato, alto volume);
- ``OPUS`` = ambíguo / disputa / handoff (raro, alto valor).

A normalização reusa o ``tokenize`` do retrieval léxico (strip-accents + lower +
stopwords), então "Não concordo!", "nao concordo" e "NÃO CONCORDO" caem no mesmo
conjunto de tokens — a decisão é estável a acento/caixa/pontuação.

O **pré-classificador LLM** (Haiku) é fase 2 explicitamente adiada (ADR-0014): só
entra se os evals provarem que a heurística erra o tier, para não adicionar um hop
ao hot path.
"""

from __future__ import annotations

from enum import StrEnum

from src.domain.knowledge.retrieval import tokenize

# ---------------------------------------------------------------------------
# Léxicos de intenção (tokens já normalizados: sem acento, minúsculos, len>=3).
# A ordem de prioridade é OPUS > HAIKU > SONNET: o tier de maior valor vence o
# empate (um "não concordo, quero falar com humano" é disputa, não FAQ).
# ---------------------------------------------------------------------------

#: Disputa / handoff / ambiguidade jurídica → OPUS (alto valor, raro).
_OPUS_TOKENS: frozenset[str] = frozenset(
    {
        "humano", "atendente", "gerente", "supervisor",
        "reclamacao", "reclamar", "reclama",
        "processo", "juridico", "advogado", "procon", "judicial",
        "concordo", "discordo", "errado", "absurdo", "indevido", "injusto",
        "cancelar", "cancelamento", "rescindir", "rescisao",
    }
)

#: Saudação / FAQ curta de KB → HAIKU (barato, alto volume).
#: Inclui termos de verbete da ``kb/`` (bandeira, prazo, sla, religacao,
#: titularidade) e aberturas curtas ("oi", "ola", "bom dia").
_HAIKU_TOKENS: frozenset[str] = frozenset(
    {
        "oi", "ola", "opa", "bom", "boa", "dia", "tarde", "noite",
        "obrigado", "obrigada", "valeu", "tchau",
        "prazo", "prazos", "sla", "bandeira", "bandeiras", "tarifa", "tarifaria",
        "titularidade", "transferir", "religacao", "religar",
    }
)

#: Transacional (fatura/outage/ticket/2ª via) → SONNET (default explícito).
#: Não dirige a decisão (SONNET já é o piso), mas documenta o caminho feliz.
#: ``conta`` é DELIBERADAMENTE omitido: é ambíguo demais ("transferir a
#: titularidade da conta" é FAQ, não transação) e forçaria o tier caro sobre
#: perguntas de KB; os sinais transacionais reais (fatura/valor/vencimento/2ª via)
#: já cobrem o caminho feliz sem precisar de "conta".
_SONNET_TOKENS: frozenset[str] = frozenset(
    {
        "fatura", "boleto", "pix", "valor", "vencimento", "pagar",
        "segunda", "via", "pdf",
        "luz", "energia", "interrupcao", "outage", "apagao", "queda", "sem",
        "chamado", "protocolo", "status", "consumo", "kwh",
    }
)

#: Mensagem muito curta (≤ N tokens) sem sinal transacional tende a ser
#: saudação/abertura → favorece HAIKU.
_CURTO_MAX_TOKENS = 3


class Modelo(StrEnum):
    """Tier de modelo escolhido por caso (ADR-0014, pilar 3)."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


def rotear_modelo(mensagem: str, *, primeiro_turno: bool = False) -> Modelo:
    """Escolhe o tier de modelo para ``mensagem`` (determinístico, sem I/O).

    Política (prioridade OPUS > HAIKU > SONNET):
    1. Qualquer sinal de **disputa/handoff/jurídico** → ``OPUS``.
    2. **Saudação/FAQ curta** (token de KB/abertura) **sem** sinal transacional
       → ``HAIKU``. Mensagem muito curta (≤3 tokens) sem sinal transacional no
       primeiro turno também cai em ``HAIKU`` (ex.: "oi, bom dia").
    3. Caso contrário → ``SONNET`` (default seguro, transacional).

    O default é ``SONNET`` mesmo para entrada vazia/sem tokens: o piso seguro
    nunca subdimensiona um caso transacional.
    """
    tokens = set(tokenize(mensagem))

    # 1) OPUS vence: disputa/handoff/jurídico é alto valor e não pode cair no tier barato.
    if tokens & _OPUS_TOKENS:
        return Modelo.OPUS

    transacional = bool(tokens & _SONNET_TOKENS)

    # 2) HAIKU: saudação/FAQ curta SEM sinal transacional.
    if not transacional:
        if tokens & _HAIKU_TOKENS:
            return Modelo.HAIKU
        # Abertura curta sem nenhum sinal forte ("oi" sozinho, "tudo bem?").
        if primeiro_turno and 0 < len(tokens) <= _CURTO_MAX_TOKENS:
            return Modelo.HAIKU

    # 3) Default seguro.
    return Modelo.SONNET


#: Mapa do tier para o id de modelo que vai em ``--model`` do ``claude -p``.
#: Aliases curtos ("haiku"/"sonnet"/"opus") são aceitos pelo Claude Code e
#: resolvem para a versão corrente — evita pinar uma data que envelhece no doc.
_CLI_FLAG: dict[Modelo, str] = {
    Modelo.HAIKU: "haiku",
    Modelo.SONNET: "sonnet",
    Modelo.OPUS: "opus",
}


def cli_model_flag(m: Modelo) -> str:
    """Traduz o tier para o valor passado em ``claude -p --model <flag>``."""
    return _CLI_FLAG[m]
