"""Fonte ÚNICA da allowlist de ferramentas do agente `luz-do-vale` (R-02).

Tudo que precisa saber *quais* tools MCP o agente pode usar — o frontmatter de
produção (tool-scoping), o tool-scope dos evals e o teste de paridade — deriva
desta lista. Antes existiam três cópias soltas (server.py, frontmatter, run.py)
e elas divergiam: o `generate_invoice_pdf` estava registrado no server mas
faltava no frontmatter e nos evals, então o agente em produção não conseguia
enviar a 2ª via. Esta fonte única + o teste de paridade
(`tests/unit/test_tool_scope_parity.py`) impedem esse drift de voltar.

Por que um módulo Python e não um `.txt`/`.yaml`:
- **Ordem estável**: a tupla preserva a ordem canônica de registro do
  `server.py` — pré-requisito do prompt caching (R-07), que exige o conjunto de
  tools na mesma ordem entre execuções.
- **Tipagem mypy-strict**: os consumidores (evals, teste) importam símbolos
  tipados, sem parsing frágil de texto.

O `server.py` continua registrando as tools com `@mcp.tool()` explícitos (as
docstrings/assinaturas tipadas que o FastMCP expõe ao agente moram lá); esta
lista NÃO substitui o registro — ela é a verdade *contratual* contra a qual o
registro do server, o frontmatter e os evals são verificados.

Fronteira de memória do agente (ADR-0013): duas tools de leitura, distintas e
read-only, ambas resolvendo o titular pelo telefone do remetente:
- ``get_account_events`` (ex-``get_conversation_context``) — FATOS DETERMINÍSTICOS
  DE SISTEMA da conta (eventos tipados gravados em ``conversation_memory`` pelo
  ProactiveService/worker, ADR-0005): pagamento confirmado, interrupção
  aberta/encerrada, último protocolo. NÃO é a transcrição da conversa.
- ``get_chat_history`` — TRANSCRIÇÃO conversacional crua (o que foi DITO no
  WhatsApp/Omni), reusando o transcript do operador (SPEC-018). Recuperação
  pós-cold-start, quando a sessão Genie reseta a janela curta/volátil.

Insights de consumo (R-17 / SPEC-025): ``get_consumption_insights`` — 12ª tool,
read-only, sumariza ~24 meses de ``consumo_kwh`` do titular (média/tendência/
sazonalidade/pico) sobre o histórico já disponível via ``list_invoices``, sem
endpoint REST novo nem LLM. Mesmo guardrail por telefone das demais tools.
"""

from __future__ import annotations

#: Prefixo do MCP server da Luz do Vale (vira ``mcp__luz-do-vale__<tool>``).
MCP_SERVER_NAME = "luz-do-vale"

#: Verbo de resposta do Omni que o agente usa para responder o WhatsApp.
#: Fica no allow do frontmatter junto das tools MCP (Bash escopado a ``omni:*``);
#: ver ``sandbox/agent/luz-do-vale.frontmatter.yaml``.
OMNI_BASH_SCOPE = "Bash(omni:*)"

#: Nomes das ferramentas na ORDEM CANÔNICA de registro do ``server.py``.
#: Manter sincronizado com os ``@mcp.tool()`` do server (garantido pelo teste de
#: paridade). NÃO reordenar sem necessidade: a ordem alimenta o cache de prompt.
TOOL_NAMES: tuple[str, ...] = (
    "find_customer_by_phone",
    "list_contracts",
    "get_invoice_status",
    "generate_invoice_pdf",
    "get_outage_by_region",
    "create_ticket",
    "get_ticket_status",
    "request_human_handoff",
    "search_knowledge_base",
    "get_account_events",
    "get_chat_history",
    "get_consumption_insights",
)


def mcp_qualified(prefix: str = MCP_SERVER_NAME) -> list[str]:
    """Nomes qualificados ``mcp__<prefix>__<tool>``, na ordem canônica.

    É a forma que o Claude Code espera em ``--allowedTools`` e em
    ``permissions.allow`` do settings.
    """
    return [f"mcp__{prefix}__{t}" for t in TOOL_NAMES]


def permissions_allow(prefix: str = MCP_SERVER_NAME) -> list[str]:
    """Bloco ``permissions.allow`` do frontmatter: tools MCP qualificadas + o
    verbo de resposta do Omni (``Bash(omni:*)``), nessa ordem.

    O frontmatter YAML continua versionado, mas deixa de ser fonte da verdade:
    o teste de paridade exige ``permissions.allow == permissions_allow()``.
    """
    return [*mcp_qualified(prefix), OMNI_BASH_SCOPE]
