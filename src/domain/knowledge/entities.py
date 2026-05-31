"""Entidades do contexto Knowledge (puras)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Artigo:
    slug: str
    titulo: str
    tags: list[str] = field(default_factory=list)
    corpo: str = ""


@dataclass(frozen=True)
class ResultadoKB:
    slug: str
    titulo: str
    trecho: str
    score: int
