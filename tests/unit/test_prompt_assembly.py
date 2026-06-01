"""Montagem única do system prompt: CAG da kb/ (R-08) + prefixo estável (R-07).

Assere que (a) os 6 verbetes reais da ``kb/`` entram no prompt montado; (b) a
ordem é estável/idempotente por slug (pré-requisito do prompt caching); e (c) o
prefixo estável NÃO contém o sufixo volátil (telefone), mantendo o bloco
cacheável byte-idêntico entre conversas. Puro, sem subprocess/LLM.
"""

from __future__ import annotations

import pathlib

from src.agent.prompt import montar_prefixo_estavel, montar_system_prompt
from src.infrastructure.knowledge import CachedFullKbStrategy, load_kb

KB_DIR = pathlib.Path(__file__).resolve().parents[2] / "kb"
AGENTS_MD = pathlib.Path(__file__).resolve().parents[2] / "agent" / "AGENTS.md"

_AGENTS_FAKE = "# Persona\nVocê é o atendente da Luz do Vale.\n"


class TestDumpKb:
    def test_inclui_todos_os_slugs_e_titulos_reais(self) -> None:
        artigos = load_kb(KB_DIR)
        assert len(artigos) >= 6
        dump = CachedFullKbStrategy(KB_DIR).dump_kb()
        for artigo in artigos:
            assert artigo.slug in dump, f"slug ausente no dump: {artigo.slug}"
            assert artigo.titulo in dump, f"titulo ausente no dump: {artigo.titulo}"

    def test_ordem_estavel_por_slug(self) -> None:
        dump = CachedFullKbStrategy(KB_DIR).dump_kb()
        slugs = [a.slug for a in load_kb(KB_DIR)]
        ordenados = sorted(slugs)
        # As posições dos cabeçalhos "### <slug>" seguem a ordem alfabética por slug.
        posicoes = [dump.index(f"### {s} ") for s in ordenados]
        assert posicoes == sorted(posicoes)

    def test_idempotente(self) -> None:
        strat = CachedFullKbStrategy(KB_DIR)
        assert strat.dump_kb() == strat.dump_kb()


class TestMontarSystemPrompt:
    def test_kb_aparece_no_prompt_montado(self) -> None:
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        prompt = montar_system_prompt(_AGENTS_FAKE, phone="555199990001", kb_block=kb)
        for artigo in load_kb(KB_DIR):
            assert artigo.slug in prompt
        assert "Base de conhecimento (pré-carregada)" in prompt

    def test_persona_vem_antes_da_kb_que_vem_antes_do_canal(self) -> None:
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        prompt = montar_system_prompt(_AGENTS_FAKE, phone="555199990001", kb_block=kb)
        i_persona = prompt.index("# Persona")
        i_kb = prompt.index("Base de conhecimento")
        i_canal = prompt.index("Contexto do canal")
        assert i_persona < i_kb < i_canal, "ordem estável→volátil quebrada (R-07)"

    def test_telefone_so_no_sufixo_volatil(self) -> None:
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        phone = "555199990001"
        prompt = montar_system_prompt(_AGENTS_FAKE, phone=phone, kb_block=kb)
        prefixo = montar_prefixo_estavel(_AGENTS_FAKE, kb_block=kb)
        assert phone in prompt
        assert phone not in prefixo, "telefone vazou para o prefixo cacheável"
        assert prompt.startswith(prefixo), "prefixo estável não é prefixo literal"

    def test_prefixo_estavel_byte_identico_entre_telefones(self) -> None:
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        a = montar_system_prompt(_AGENTS_FAKE, phone="555100000001", kb_block=kb)
        b = montar_system_prompt(_AGENTS_FAKE, phone="555100000002", kb_block=kb)
        prefixo = montar_prefixo_estavel(_AGENTS_FAKE, kb_block=kb)
        # Só o sufixo (telefone) difere; o prefixo cacheável é idêntico.
        assert a[: len(prefixo)] == b[: len(prefixo)] == prefixo

    def test_sem_kb_block_omite_secao(self) -> None:
        prompt = montar_system_prompt(_AGENTS_FAKE, phone="555199990001", kb_block=None)
        assert "Base de conhecimento" not in prompt
        assert "555199990001" in prompt

    def test_phone_none_devolve_so_prefixo(self) -> None:
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        prompt = montar_system_prompt(_AGENTS_FAKE, phone=None, kb_block=kb)
        assert "Contexto do canal" not in prompt
        assert prompt == montar_prefixo_estavel(_AGENTS_FAKE, kb_block=kb)


class TestParidadeComAgentsReal:
    """O AGENTS.md real entra inteiro no prefixo (paridade eval↔produção, M-07)."""

    def test_agents_md_real_no_prefixo(self) -> None:
        agents_md = AGENTS_MD.read_text(encoding="utf-8")
        kb = CachedFullKbStrategy(KB_DIR).dump_kb()
        prompt = montar_system_prompt(agents_md, phone="555199990001", kb_block=kb)
        assert "Regras invioláveis (guardrails)" in prompt
        assert "find_customer_by_phone" in prompt
