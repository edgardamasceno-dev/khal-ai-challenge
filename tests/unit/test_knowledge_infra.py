from __future__ import annotations

import pathlib

from src.infrastructure.knowledge import FilesystemKnowledgeRetrieval, load_kb

KB_DIR = pathlib.Path(__file__).resolve().parents[2] / "kb"

_ARTIGO_MD = """\
---
titulo: Religacao apos corte
tags: religacao, corte, restabelecer
---
Para religar, quite o debito. A religacao ocorre em ate 24h.
"""


class TestLoader:
    def test_parse_frontmatter_e_slug(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "religacao.md").write_text(_ARTIGO_MD, encoding="utf-8")
        artigos = load_kb(tmp_path)
        assert len(artigos) == 1
        a = artigos[0]
        assert a.slug == "religacao"
        assert a.titulo == "Religacao apos corte"
        assert a.tags == ["religacao", "corte", "restabelecer"]
        assert "quite o debito" in a.corpo
        assert "---" not in a.corpo  # frontmatter removido

    def test_adapter_busca_no_corpus_temporario(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "religacao.md").write_text(_ARTIGO_MD, encoding="utf-8")
        repo = FilesystemKnowledgeRetrieval(tmp_path)
        res = repo.search("religacao corte", limit=3)
        assert res and res[0].slug == "religacao"
        assert repo.search("assunto inexistente zzz", limit=3) == []


class TestCorpusReal:
    def test_carrega_kb_do_repo(self) -> None:
        artigos = load_kb(KB_DIR)
        slugs = {a.slug for a in artigos}
        assert len(artigos) >= 6
        assert {"titularidade", "religacao", "segunda-via"} <= slugs

    def test_busca_titularidade_no_corpus_real(self) -> None:
        repo = FilesystemKnowledgeRetrieval(KB_DIR)
        res = repo.search("como transferir a titularidade da conta", limit=3)
        assert res[0].slug == "titularidade"
        assert res[0].trecho
