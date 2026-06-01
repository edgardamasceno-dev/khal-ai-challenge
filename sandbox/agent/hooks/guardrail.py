#!/usr/bin/env python3
"""Hook de guardrail determinístico do Claude Code (R-20 / ADR-0020).

Reforça os guardrails do agente CX `luz-do-vale` na borda do RUNTIME do Claude
Code, em complemento — não em substituição — às camadas que já existem:

  1. Tool-scoping (frontmatter: allow/deny + ``--disallowedTools``);
  2. Rede só-MCP + egress allowlist (compose.sandbox.yml);
  3. Validação/idempotência/escopo-por-telefone DENTRO do MCP server.

Este hook adiciona uma 4ª camada *no agente*, barata e determinística:

  - **PreToolUse**: bloqueia tool fora da allowlist canônica; bloqueia escrita
    (``create_ticket``) sem ``confirmar=true``; bloqueia acesso a telefone
    diferente do remetente do turno (anti-injection de identidade).
  - **UserPromptSubmit**: bloqueia padrões óbvios de prompt-injection
    ("ignore as instruções anteriores", "revele o system prompt", ...).

CONTRATO DO CLAUDE CODE (hooks):
  - O evento chega como JSON no STDIN.
  - ``exit 0`` = permite (allow). ``exit 2`` = bloqueia (deny); o texto em STDERR
    volta ao modelo como motivo. Qualquer outro exit code é tratado como erro
    não-bloqueante pelo Claude Code (fail-open) — por isso mantemos só 0/2.

A LÓGICA é pura e isolada em ``decidir(evento)`` para ser 100% unit-testável
(``tests/unit/test_guardrail_hook.py``), sem subir o agente. O ``main()`` é só o
adaptador de I/O (stdin→decisão→exit code). Sem dependências externas (stdlib),
para rodar no Python do sandbox sem instalar nada.

NOTA (validação ao vivo): o *disparo* deste hook pelo Claude Code dentro do
sandbox depende do registro em ``settings.json`` (escopo user, claude-home) e de
o runtime do Genie spawnar o Claude com esse settings — é CONFIG + validação ao
vivo. A decisão em si é testada offline.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

#: Allowlist canônica de tools MCP qualificadas (``mcp__luz-do-vale__<tool>``).
#: DERIVADA de ``src/interfaces/mcp/allowlist.py`` (fonte única, R-02). É
#: duplicada aqui de propósito: o sandbox NÃO tem o ``src/`` Python montado em
#: runtime, então o hook precisa ser autossuficiente (stdlib-only). A paridade
#: com a allowlist Python é garantida no teste ``test_guardrail_hook.py``, que
#: importa ambas e exige igualdade — qualquer drift FALHA o CI.
MCP_SERVER_NAME = "luz-do-vale"
ALLOWED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        f"mcp__{MCP_SERVER_NAME}__{t}"
        for t in (
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
    }
)

#: Tools de ESCRITA que exigem confirmação explícita antes de executar (ADR/guardrail
#: de "confirmação obrigatória antes de escrita"). ``create_ticket`` abre chamado.
WRITE_TOOLS_REQUIRING_CONFIRMATION: frozenset[str] = frozenset(
    {f"mcp__{MCP_SERVER_NAME}__create_ticket"}
)

#: Tools que recebem um ``phone``/``telefone`` e DEVEM bater com o remetente do
#: turno — o agente só atende o titular resolvido pelo telefone de quem mandou a
#: mensagem (guardrail "acesso só ao titular", não contornável por injection).
PHONE_SCOPED_TOOLS: frozenset[str] = ALLOWED_MCP_TOOLS

#: Padrões óbvios de prompt-injection no texto do usuário. Heurística
#: determinística (não um classificador): pega os ataques de manual; o resto fica
#: para a camada probabilística (policy + evals). Normalizado (sem acento, lower).
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore (as |todas as |todas )?(instrucoes|regras)( anteriores| acima)?"),
    re.compile(r"ignore (all |any |the )*(previous |above )?(instructions|rules)"),
    re.compile(r"(revele|mostre|exiba|imprima) (o |seu )?(system ?prompt|prompt do sistema)"),
    re.compile(r"(reveal|show|print|repeat) (the |your )?(system ?prompt|instructions)"),
    re.compile(r"voce agora e (um|uma) "),
    re.compile(r"you are now (a |an )?"),
    re.compile(r"(esqueca|disregard|forget) (tudo|todas|all|everything)"),
    re.compile(r"developer mode|modo desenvolvedor|jailbreak|dan mode"),
)


def _normalizar(texto: str) -> str:
    """Minúsculas + sem acentos (NFKD). Reusa a mesma estratégia de normalização
    do retrieval léxico (``knowledge``) para casar padrões de forma estável,
    independente de acento/caixa."""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _digitos(valor: object) -> str:
    """Só os dígitos de um identificador de telefone/LID. Tolera ``None``/não-str
    e formatos com ``+``, espaços, ``@lid``: compara identidades por dígitos."""
    if not isinstance(valor, str):
        return ""
    return re.sub(r"\D", "", valor)


def _decidir_pre_tool_use(evento: dict[str, object]) -> tuple[bool, str]:
    """Decisão para PreToolUse. ``tool_name`` + ``tool_input`` (contrato do hook).

    O remetente do turno chega via ``GENIE_OMNI_CHAT_ID`` no env do hook,
    repassado pelo chamador em ``evento['_sender']`` (o ``main`` injeta). Sem ele,
    NÃO bloqueia por telefone (fail-open só nessa checagem específica: a ausência
    do contexto de canal não deve travar o agente; as demais checagens valem)."""
    tool_name = evento.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        # Sem nome de tool não há o que avaliar — deixa passar (outras camadas
        # pegam). Hook PreToolUse sem tool_name é evento malformado/ruído.
        return True, ""

    # Tools não-MCP (ex.: Bash(omni:*) p/ responder) não são deste hook: o
    # tool-scoping do frontmatter já as restringe. Só governamos as MCP daqui.
    if tool_name.startswith("mcp__") and tool_name not in ALLOWED_MCP_TOOLS:
        return False, (
            f"Tool MCP fora da allowlist do agente: {tool_name}. "
            "Use apenas as ferramentas da Luz do Vale autorizadas."
        )

    tool_input = evento.get("tool_input")
    args: dict[str, object] = tool_input if isinstance(tool_input, dict) else {}

    # Escrita exige confirmação explícita (create_ticket).
    if tool_name in WRITE_TOOLS_REQUIRING_CONFIRMATION:
        confirmar = args.get("confirmar")
        if confirmar is not True:
            return False, (
                f"{tool_name} é ação de escrita e exige confirmacao=true do "
                "cliente antes de executar (confirmação obrigatória)."
            )

    # Acesso só ao titular do remetente: se a tool recebe phone/telefone e há um
    # remetente conhecido, eles têm de bater (por dígitos, tolerando +/espaços/LID).
    sender = evento.get("_sender")
    if tool_name in PHONE_SCOPED_TOOLS and isinstance(sender, str) and _digitos(sender):
        alvo = args.get("phone", args.get("telefone"))
        alvo_dig = _digitos(alvo)
        if alvo_dig and alvo_dig != _digitos(sender):
            return False, (
                "Acesso negado: o telefone consultado difere do remetente do "
                "turno. O agente só atende o titular que enviou a mensagem."
            )

    return True, ""


def _decidir_user_prompt_submit(evento: dict[str, object]) -> tuple[bool, str]:
    """Decisão para UserPromptSubmit. Bloqueia prompt-injection óbvio no
    ``prompt`` do usuário. Heurística determinística; o resto é da camada de
    policy/evals."""
    prompt = evento.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return True, ""
    alvo = _normalizar(prompt)
    for pat in _INJECTION_PATTERNS:
        if pat.search(alvo):
            return False, (
                "Mensagem bloqueada por tentativa de manipulação das instruções "
                "do agente (prompt injection). Atenda apenas pedidos legítimos de "
                "atendimento da Luz do Vale."
            )
    return True, ""


def decidir(evento: dict[str, object]) -> tuple[bool, str]:
    """Decisão PURA do guardrail: ``(permitido, motivo)``.

    Roteia por ``hook_event_name`` (contrato do Claude Code): ``PreToolUse`` ou
    ``UserPromptSubmit``. Eventos de outros tipos (ou desconhecidos) são
    permitidos (fail-open) — este hook só governa os dois pontos para os quais
    foi registrado. ``motivo`` só é preenchido quando ``permitido`` é ``False``.

    Determinístico: a mesma entrada produz sempre a mesma decisão.
    """
    nome = evento.get("hook_event_name")
    if nome == "PreToolUse":
        return _decidir_pre_tool_use(evento)
    if nome == "UserPromptSubmit":
        return _decidir_user_prompt_submit(evento)
    return True, ""


def main() -> int:
    """Adaptador de I/O: lê o evento JSON do STDIN, injeta o remetente do canal
    (env ``GENIE_OMNI_CHAT_ID``), decide e mapeia para o exit code do contrato do
    hook (0=allow, 2=block, motivo no STDERR).

    Fail-open em erro de parsing: se o STDIN não for JSON válido, NÃO bloqueia
    (exit 0) — um hook quebrado não pode derrubar o atendimento; as outras
    camadas de guardrail seguem ativas.
    """
    import os

    raw = sys.stdin.read()
    try:
        evento = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(evento, dict):
        return 0

    sender = os.environ.get("GENIE_OMNI_CHAT_ID")
    if sender and "_sender" not in evento:
        evento["_sender"] = sender

    permitido, motivo = decidir(evento)
    if permitido:
        return 0
    print(motivo, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
