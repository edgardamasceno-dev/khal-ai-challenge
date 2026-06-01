"""Teste de PARIDADE da allowlist de ferramentas (R-02) — anti-drift.

Antes, a lista de tools do agente vivia copiada em três lugares que divergiam:
o registro do ``server.py``, o ``permissions.allow`` do frontmatter de produção
e a lista ``TOOLS`` dos evals. O ``generate_invoice_pdf`` estava registrado no
server mas FALTAVA no frontmatter e nos evals — então o agente em produção não
podia enviar a 2ª via (bug de contrato R-02).

A correção é uma fonte única (``src/interfaces/mcp/allowlist.py``); este teste
garante que as três fontes derivadas continuam idênticas a ela. Roda em
``make check`` / CI e BLOQUEIA qualquer PR que reintroduza a divergência
(tool registrada fora da allowlist, ou allowlist com tool não registrada, ou
frontmatter/evals fora de sincronia).
"""

from __future__ import annotations

import pathlib

import yaml

from src.interfaces.mcp import allowlist
from src.interfaces.mcp import server as mcp_server

REPO = pathlib.Path(__file__).resolve().parents[2]
FRONTMATTER_PATH = REPO / "sandbox" / "agent" / "luz-do-vale.frontmatter.yaml"


def _server_registered_names() -> set[str]:
    """Nomes das tools efetivamente registradas no FastMCP do ``server.py``.

    Lê o registry interno do FastMCP (introspecção das funções decoradas com
    ``@mcp.tool()``), sem subir o transporte HTTP nem tocar o DB — importar o
    server degrada a auditoria para no-op quando não há ``DATABASE_URL``.
    """
    return set(mcp_server.mcp._tool_manager._tools.keys())


def test_parity_server_equals_allowlist() -> None:
    """(1) SERVER == ALLOWLIST: as tools registradas no ``server.py`` são
    exatamente as da fonte única — nem a mais (tool órfã fora da allowlist), nem
    a menos (allowlist citando tool não registrada). Cobre o bug do PDF."""
    registradas = _server_registered_names()
    canonicas = set(allowlist.TOOL_NAMES)
    so_no_server = registradas - canonicas
    so_na_allowlist = canonicas - registradas
    assert not so_no_server, (
        f"Tool registrada no server.py fora da allowlist: {sorted(so_no_server)}. "
        "Adicione em src/interfaces/mcp/allowlist.py::TOOL_NAMES."
    )
    assert not so_na_allowlist, (
        f"Tool na allowlist sem registro no server.py: {sorted(so_na_allowlist)}. "
        "Registre-a com @mcp.tool() ou remova da allowlist."
    )


def test_allowlist_has_no_duplicates_and_stable_order() -> None:
    """A ordem é pré-requisito do prompt caching (R-07): sem duplicatas e
    estável. Garante que ``TOOL_NAMES`` é uma sequência limpa antes de comparar
    ordens nas assertivas seguintes."""
    nomes = list(allowlist.TOOL_NAMES)
    assert len(nomes) == len(set(nomes)), f"allowlist com duplicatas: {nomes}"


def test_parity_evals_equals_allowlist_same_order() -> None:
    """(2) EVAL == ALLOWLIST (MESMA ORDEM): o tool-scope dos evals deriva da
    fonte única. Ordem idêntica preserva o cache de prompt (R-07) entre runs."""
    from src.evals.run import ALLOWED, TOOLS

    assert list(allowlist.TOOL_NAMES) == TOOLS, (
        "src.evals.run.TOOLS divergiu da allowlist (ordem importa). "
        f"evals={TOOLS!r} allowlist={list(allowlist.TOOL_NAMES)!r}"
    )
    assert allowlist.mcp_qualified() == ALLOWED, (
        "src.evals.run.ALLOWED (qualificadas) divergiu de allowlist.mcp_qualified()."
    )


def test_parity_frontmatter_equals_allowlist() -> None:
    """(3) FRONTMATTER == ALLOWLIST: o ``permissions.allow`` do frontmatter de
    produção é exatamente ``permissions_allow()`` (tools MCP qualificadas na
    ordem canônica + ``Bash(omni:*)`` ao final), sem órfãos."""
    data = yaml.safe_load(FRONTMATTER_PATH.read_text(encoding="utf-8"))
    allow = data["permissions"]["allow"]
    esperado = allowlist.permissions_allow()
    assert allow == esperado, (
        "permissions.allow do frontmatter divergiu da fonte única "
        "(src/interfaces/mcp/allowlist.py::permissions_allow). "
        f"frontmatter={allow!r} esperado={esperado!r}"
    )
    # Nenhuma entrada órfã de MCP no allow (qualquer mcp__luz-do-vale__* tem de
    # estar na allowlist qualificada).
    qualificadas = set(allowlist.mcp_qualified())
    orfas = {
        item
        for item in allow
        if item.startswith("mcp__luz-do-vale__") and item not in qualificadas
    }
    assert not orfas, f"Entradas MCP órfãs em permissions.allow: {sorted(orfas)}"


def test_pdf_and_memory_tools_present_in_all_sources() -> None:
    """BÔNUS — regressão explícita dos bugs R-02 (PDF) e R-03 (memória) e da
    fronteira de memória do ADR-0013: ``generate_invoice_pdf``,
    ``get_account_events`` (ex-``get_conversation_context``, EVENTOS de sistema)
    e ``get_chat_history`` (TRANSCRIÇÃO conversacional) aparecem nas TRÊS fontes
    (server, evals, frontmatter), via a fonte única."""
    from src.evals.run import TOOLS

    fm = yaml.safe_load(FRONTMATTER_PATH.read_text(encoding="utf-8"))
    fm_allow = set(fm["permissions"]["allow"])
    server_names = _server_registered_names()

    for tool in ("generate_invoice_pdf", "get_account_events", "get_chat_history"):
        assert tool in allowlist.TOOL_NAMES, f"{tool} ausente da allowlist"
        assert tool in TOOLS, f"{tool} ausente do tool-scope dos evals"
        assert tool in server_names, f"{tool} não registrada no server.py"
        assert f"mcp__luz-do-vale__{tool}" in fm_allow, f"{tool} ausente do frontmatter"


def test_allowlist_has_exactly_eleven_tools() -> None:
    """O contrato R-02 fecha em 11 tools (catálogo completo: PDF + as duas tools
    de memória do ADR-0013, ``get_account_events`` e ``get_chat_history``).
    Trava o tamanho para flagrar adição/remoção silenciosa."""
    assert len(allowlist.TOOL_NAMES) == 11, (
        f"esperadas 11 tools no catálogo, encontradas {len(allowlist.TOOL_NAMES)}: "
        f"{list(allowlist.TOOL_NAMES)}"
    )
