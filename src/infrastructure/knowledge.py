"""Adapter de KB no filesystem (ADR-0004): carrega os markdown de `kb/` e
ranqueia por busca lexica. Implementa o KnowledgeRetrievalPort.
"""

from __future__ import annotations

import pathlib

from src.domain.knowledge.entities import Artigo, ResultadoKB
from src.domain.knowledge.retrieval import rank


def _parse_frontmatter(text: str) -> tuple[str, list[str], str]:
    titulo = ""
    tags: list[str] = []
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            header, body = parts[1], parts[2]
            for line in header.splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key == "titulo":
                    titulo = value
                elif key == "tags":
                    tags = [t.strip() for t in value.split(",") if t.strip()]
    return titulo, tags, body.strip()


def load_kb(kb_dir: pathlib.Path) -> list[Artigo]:
    artigos: list[Artigo] = []
    for path in sorted(kb_dir.glob("*.md")):
        titulo, tags, corpo = _parse_frontmatter(path.read_text(encoding="utf-8"))
        artigos.append(Artigo(slug=path.stem, titulo=titulo or path.stem, tags=tags, corpo=corpo))
    return artigos


class FilesystemKnowledgeRetrieval:
    """Strategy de retrieval lexico sobre `kb/` (carrega uma vez na construcao)."""

    def __init__(self, kb_dir: pathlib.Path) -> None:
        self._artigos = load_kb(kb_dir)

    def search(self, query: str, limit: int) -> list[ResultadoKB]:
        return rank(self._artigos, query, limit)
