"""Resumo extrativo determinístico de uma thread (R-15 / SPEC-028).

Fallback **default** do resumo de thread: heurística pura, **sem LLM**, sempre
disponível, idempotente e 100% unit-testável. Respeita o princípio "sem LLM no
caminho crítico" (ADR-0005/ADR-0019): o fechamento de ticket/handoff nunca
depende de uma chamada de rede para registrar o resumo na memória.

A heurística é extrativa (não abstrativa): seleciona trechos reais da conversa
— a 1ª mensagem do cliente (o motivo do contato) + as últimas N trocas (o
desfecho) — prefixando o autor (`[cliente]`/`[agente]`) e truncando no limite.
"""

from __future__ import annotations

from src.domain.conversation.entities import MensagemChat

# Quantas das ÚLTIMAS mensagens (desfecho) entram no resumo, além da 1ª do cliente.
_ULTIMAS_TROCAS = 4
_SEM_CONTEUDO = "[sem conteúdo de conversa]"


def _rotulo(msg: MensagemChat) -> str:
    return "[cliente]" if msg.do_cliente else "[agente]"


def _linha(msg: MensagemChat) -> str:
    """Uma linha `[autor] texto` com o texto normalizado (espaços colapsados)."""
    texto = " ".join(msg.texto.split())
    return f"{_rotulo(msg)} {texto}"


def _truncar(texto: str, max_chars: int) -> str:
    """Trunca preservando o limite; sinaliza o corte com reticências (cabem no limite)."""
    if max_chars <= 0 or len(texto) <= max_chars:
        return texto
    if max_chars <= 1:
        return texto[:max_chars]
    return texto[: max_chars - 1].rstrip() + "…"


def resumo_extrativo(mensagens: list[MensagemChat], *, max_chars: int = 600) -> str:
    """Resumo extrativo determinístico de uma thread.

    Seleção: a 1ª mensagem **do cliente** (motivo do contato) seguida das últimas
    `_ULTIMAS_TROCAS` mensagens (desfecho), sem repetir a 1ª se ela já cair nesse
    rabo. Cada linha vem prefixada por `[cliente]`/`[agente]`. O conjunto é
    truncado em `max_chars`. Determinístico e idempotente: as mesmas mensagens
    produzem sempre o mesmo texto (pré-requisito para gravar uma só vez na memória).
    """
    uteis = [m for m in mensagens if m.texto and m.texto.strip()]
    if not uteis:
        return _SEM_CONTEUDO

    selecionadas: list[MensagemChat] = []
    vistos: set[str] = set()

    primeira_cliente = next((m for m in uteis if m.do_cliente), None)
    if primeira_cliente is not None:
        selecionadas.append(primeira_cliente)
        vistos.add(primeira_cliente.id)

    for m in uteis[-_ULTIMAS_TROCAS:]:
        if m.id not in vistos:
            selecionadas.append(m)
            vistos.add(m.id)

    bloco = "\n".join(_linha(m) for m in selecionadas)
    return _truncar(bloco, max_chars)
