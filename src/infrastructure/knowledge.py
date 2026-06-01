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


def render_kb_block(artigos: list[Artigo]) -> str:
    """Concatena os verbetes num bloco markdown ESTAVEL e ordenado por slug.

    Ordem canonica (``sorted`` por slug) -> bytes identicos entre execucoes, o
    que e pre-requisito do prompt caching (R-07): o prefixo cacheavel so da hit
    se for byte-a-byte igual turno a turno. Cada verbete vira uma subsecao
    ``### <slug> — <titulo>`` seguida do corpo, sem o frontmatter (ja removido no
    ``load_kb``). Funcao pura: mesma lista -> mesma string.
    """
    blocos: list[str] = []
    for artigo in sorted(artigos, key=lambda a: a.slug):
        blocos.append(f"### {artigo.slug} — {artigo.titulo}\n{artigo.corpo.strip()}")
    return "\n\n".join(blocos)


class CachedFullKbStrategy:
    """Strategy CAG (ADR-0004/0014): carrega a `kb/` INTEIRA uma vez e a expoe
    tanto por ``search`` (mantem o contrato do ``KnowledgeRetrievalPort``) quanto
    por ``dump_kb``, que serializa os 6 verbetes num bloco estavel para ir no
    prefixo cacheavel do system prompt (R-08).

    Para a escala atual (6 verbetes / ~3,5 KB) carregar tudo no contexto custa
    menos que uma ida-e-volta ao MCP por turno; ``search_knowledge_base`` segue
    como FALLBACK para perguntas fora dos verbetes pre-carregados (ADR-0014).
    """

    def __init__(self, kb_dir: pathlib.Path) -> None:
        self._artigos = load_kb(kb_dir)

    def search(self, query: str, limit: int) -> list[ResultadoKB]:
        return rank(self._artigos, query, limit)

    def dump_kb(self) -> str:
        """Bloco markdown estavel com TODOS os verbetes, ordenado por slug.

        Idempotente: chamadas repetidas devolvem a mesma string (cache-friendly).
        """
        return render_kb_block(self._artigos)
