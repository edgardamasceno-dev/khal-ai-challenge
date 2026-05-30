from __future__ import annotations

from src.domain.knowledge.entities import Artigo
from src.domain.knowledge.retrieval import rank, tokenize

A_REL = Artigo(
    slug="religacao",
    titulo="Religacao apos pagamento de debito",
    tags=["religacao", "corte", "restabelecer"],
    corpo="Para religar a unidade, quite o debito em aberto. A religacao ocorre em ate 24h.",
)
A_TIT = Artigo(
    slug="titularidade",
    titulo="Transferencia de titularidade",
    tags=["titularidade", "transferir", "nome"],
    corpo="Para transferir a titularidade da conta, apresente os documentos do novo titular.",
)
A_2VIA = Artigo(
    slug="segunda-via",
    titulo="Segunda via da fatura",
    tags=["segunda via", "fatura", "boleto"],
    corpo="Voce pode emitir a segunda via da fatura pelo aplicativo ou pelo WhatsApp.",
)
CORPUS = [A_REL, A_TIT, A_2VIA]


class TestTokenize:
    def test_remove_acentos_stopwords_e_curtos(self) -> None:
        toks = tokenize("Como faço para a Religação?")
        assert "religacao" in toks
        assert "para" not in toks  # stopword
        assert "a" not in toks  # curto

    def test_query_acentuada_casa_corpo_sem_acento(self) -> None:
        assert "titularidade" in tokenize("titularidade")


class TestRank:
    def test_query_relevante_no_topo(self) -> None:
        res = rank(CORPUS, "como transferir a titularidade", limit=3)
        assert res[0].slug == "titularidade"

    def test_tags_pontuam(self) -> None:
        res = rank(CORPUS, "religacao corte", limit=3)
        assert res[0].slug == "religacao"

    def test_sem_match_retorna_vazio(self) -> None:
        assert rank(CORPUS, "assunto totalmente inexistente zzz", limit=3) == []

    def test_query_vazia_retorna_vazio(self) -> None:
        assert rank(CORPUS, "   ", limit=3) == []

    def test_respeita_limit(self) -> None:
        res = rank(CORPUS, "fatura titularidade religacao", limit=1)
        assert len(res) == 1

    def test_boost_de_titulo_sobre_corpo(self) -> None:
        no_titulo = Artigo("a", "Boleto e pagamento", [], "texto qualquer")
        no_corpo = Artigo("b", "Outro assunto", [], "fale sobre boleto aqui no corpo")
        res = rank([no_corpo, no_titulo], "boleto", limit=2)
        assert res[0].slug == "a"  # titulo tem mais peso

    def test_resultado_tem_trecho_e_score(self) -> None:
        res = rank(CORPUS, "titularidade", limit=1)
        assert res[0].score > 0
        assert "titularidade" in res[0].trecho.lower()
