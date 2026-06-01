"""Roteador de modelo determinístico por caso (R-09 / ADR-0014, pilar 3).

Heurística **pura** (sem I/O, sem hop de LLM) que mapeia a mensagem do cliente em
um tier de modelo, materializando a política do ADR-0014:

- ``SONNET`` = default seguro (transacional **e abertura/saudação**: fatura,
  outage, ticket, 2ª via, e o **fan-out de abertura** que lê a conta);
- ``HAIKU`` = **FAQ pura de KB** (verbete sem contexto de conta: bandeira, prazo,
  SLA, religação, titularidade) — barato, alto volume;
- ``OPUS`` = ambíguo / disputa / handoff (raro, alto valor).

A saudação/abertura (ex.: "oi", "bom dia") **deixa de ir para HAIKU**: o 1º turno
dispara o fan-out de abertura (``find_customer_by_phone`` + ``get_account_events``
+ ``get_invoice_status``/``get_outage_by_region``), e o tier barato tende a
conversar e **pular as tool-calls**. Abertura com contexto de conta → ``SONNET``
(ADR-0014, ajuste pós-eval Passada 1). ``HAIKU`` fica restrito a FAQ de KB pura.

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

#: **FAQ pura de KB** → HAIKU (barato, alto volume). Apenas termos de **verbete**
#: da ``kb/`` (bandeira, prazo, sla, religacao, titularidade) — conhecimento geral
#: que NÃO depende de ler a conta do cliente.
#: Saudação/abertura ("oi", "ola", "bom dia") foi DELIBERADAMENTE removida daqui:
#: o 1º turno aciona o fan-out de abertura (find_customer + get_account_events), e o
#: tier barato pula as tool-calls (FAILs J10/J11 da Passada 1). Abertura → SONNET.
_HAIKU_TOKENS: frozenset[str] = frozenset(
    {
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

class Modelo(StrEnum):
    """Tier de modelo escolhido por caso (ADR-0014, pilar 3)."""

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


def rotear_modelo(mensagem: str, *, primeiro_turno: bool = False) -> Modelo:
    """Escolhe o tier de modelo para ``mensagem`` (determinístico, sem I/O).

    Política (prioridade OPUS > HAIKU > SONNET):
    1. Qualquer sinal de **disputa/handoff/jurídico** → ``OPUS``.
    2. **FAQ pura de KB** (token de verbete da ``kb/``) **sem** sinal transacional
       → ``HAIKU`` (ex.: "qual o prazo de religação?", "o que é bandeira tarifária?").
    3. Caso contrário → ``SONNET`` (default seguro): transacional **e também
       saudação/abertura** ("oi", "bom dia"), porque o 1º turno aciona o fan-out de
       abertura (find_customer + get_account_events) e o tier barato pula as
       tool-calls. O parâmetro ``primeiro_turno`` é mantido por compatibilidade de
       assinatura, mas não muda mais a decisão (abertura não vai para HAIKU).

    O default é ``SONNET`` mesmo para entrada vazia/sem tokens: o piso seguro
    nunca subdimensiona um caso transacional nem uma abertura.
    """
    del primeiro_turno  # não influencia mais a decisão (abertura → SONNET, não HAIKU).
    tokens = set(tokenize(mensagem))

    # 1) OPUS vence: disputa/handoff/jurídico é alto valor e não pode cair no tier barato.
    if tokens & _OPUS_TOKENS:
        return Modelo.OPUS

    transacional = bool(tokens & _SONNET_TOKENS)

    # 2) HAIKU: FAQ pura de KB SEM sinal transacional (verbete sem contexto de conta).
    if not transacional and (tokens & _HAIKU_TOKENS):
        return Modelo.HAIKU

    # 3) Default seguro: transacional, abertura/saudação e desconhecido.
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
