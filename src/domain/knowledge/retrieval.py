"""Retrieval lexico puro (sem I/O): tokenize + ranking com boost de titulo/tags
e extracao de trecho. ADR-0004 (estrategia filesystem/lexico do MVP).
"""

from __future__ import annotations

import re
import unicodedata

from src.domain.knowledge.entities import Artigo, ResultadoKB

_STOPWORDS = {
    "de", "da", "do", "para", "com", "em", "no", "na", "como", "que", "um", "uma",
    "por", "se", "ao", "os", "as", "meu", "minha", "sua", "seu", "faco", "fazer",
    "quero", "sobre", "pelo", "pela", "dos", "das", "mais", "voce",
}
_MIN_LEN = 3
_TITULO_BOOST = 3
_TAGS_BOOST = 2
_TRECHO_MAX = 240


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    normalized = _strip_accents(text.lower())
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [t for t in tokens if len(t) >= _MIN_LEN and t not in _STOPWORDS]


def _score(artigo: Artigo, query_tokens: set[str]) -> int:
    titulo = tokenize(artigo.titulo)
    tags = tokenize(" ".join(artigo.tags))
    corpo = tokenize(artigo.corpo)
    total = 0
    for qt in query_tokens:
        total += _TITULO_BOOST * titulo.count(qt)
        total += _TAGS_BOOST * tags.count(qt)
        total += corpo.count(qt)
    return total


def _trecho(corpo: str, query_tokens: set[str]) -> str:
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", corpo) if p.strip()]
    for paragrafo in paragrafos:
        if query_tokens & set(tokenize(paragrafo)):
            return paragrafo[:_TRECHO_MAX]
    fallback = paragrafos[0] if paragrafos else corpo.strip()
    return fallback[:_TRECHO_MAX]


def rank(artigos: list[Artigo], query: str, limit: int) -> list[ResultadoKB]:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return []
    scored = [(s, a) for a in artigos if (s := _score(a, query_tokens)) > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].slug))
    return [
        ResultadoKB(slug=a.slug, titulo=a.titulo, trecho=_trecho(a.corpo, query_tokens), score=s)
        for s, a in scored[:limit]
    ]
