"""Runner ao vivo dos evals: dirige `claude -p` (headless, sem key - ADR-0007)
por jornada contra o `/mcp`, e avalia com as assercoes de journeys.py.

    python -m src.evals.run            # todas as jornadas
    python -m src.evals.run J1 cross   # filtra por nome
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

from src.agent.model_router import Modelo, cli_model_flag, rotear_modelo
from src.agent.prompt import montar_system_prompt
from src.evals.harness import AgentRun, parse_run
from src.evals.journeys import SCENARIOS
from src.infrastructure.knowledge import CachedFullKbStrategy
from src.interfaces.mcp.allowlist import TOOL_NAMES, mcp_qualified

REPO = pathlib.Path(__file__).resolve().parents[2]
AGENT_DIR = REPO / "agent"
KB_DIR = REPO / "kb"

# CAG (R-08): a kb/ inteira pre-carregada UMA vez e injetada no prefixo estavel do
# system prompt (montar_system_prompt) — o mesmo bloco que o sandbox monta no
# AGENTS.md final (paridade M-07). search_knowledge_base segue como fallback.
_KB_STRATEGY = CachedFullKbStrategy(KB_DIR)
# Fonte ÚNICA: o tool-scope dos evals deriva da allowlist (R-02), na mesma ordem
# canônica do server.py — sem lista hardcoded que diverge de produção.
TOOLS = list(TOOL_NAMES)
ALLOWED = mcp_qualified()

# Gate de qualidade do agente (R-01): o CI reprova o merge quando o score < limiar.
# Default 85 (docs/11). Configurável por env: EVAL_GATE_MIN (nome usado no ci.yml)
# tem prioridade sobre EVAL_GATE; ambos aceitos para não acoplar o contrato a um nome.
_DEFAULT_GATE = 85


def compute_score(passed: int, total: int) -> int:
    """Score 0-100 determinístico: ``round(100 * PASS / TOTAL)``.

    Suíte vazia (``total == 0``) => 0 (sem evidência de qualidade não é aprovação).
    """
    if total <= 0:
        return 0
    return round(100 * passed / total)


def gate_threshold() -> int:
    """Limiar do gate (default 85). ``EVAL_GATE_MIN`` (ci.yml) precede ``EVAL_GATE``."""
    raw = os.environ.get("EVAL_GATE_MIN") or os.environ.get("EVAL_GATE")
    if raw is None or raw.strip() == "":
        return _DEFAULT_GATE
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_GATE


def gate_passes(score: int, threshold: int) -> bool:
    """O gate passa quando o score atinge ou supera o limiar (``>=``)."""
    return score >= threshold


def build_system_prompt(phone: str) -> str:
    """Monta o system prompt do turno pela funcao UNICA (R-07/R-08).

    Prefixo estavel = AGENTS.md + CAG da kb/ (cacheavel); sufixo volatil =
    telefone do remetente. Mesma montagem do sandbox (paridade M-07).
    """
    agents_md = (AGENT_DIR / "AGENTS.md").read_text(encoding="utf-8")
    return montar_system_prompt(agents_md, phone=phone, kb_block=_KB_STRATEGY.dump_kb())


def run_agent(phone: str, message: str, *, modelo: Modelo | None = None) -> AgentRun:
    sysprompt = build_system_prompt(phone)
    # R-09: tier de modelo deterministico por caso (saudacao=haiku, transacional=
    # sonnet, disputa/handoff=opus). primeiro_turno=True: o runner dispara 1 turno
    # por jornada, que e sempre a abertura da conversa.
    tier = modelo or rotear_modelo(message, primeiro_turno=True)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(sysprompt)
        spfile = f.name
    cmd = [
        "claude", "-p", message,
        "--model", cli_model_flag(tier),
        "--append-system-prompt-file", spfile,
        "--mcp-config", str(AGENT_DIR / "mcp.config.json"),
        "--allowedTools", *ALLOWED,
        "--permission-mode", "bypassPermissions",
        "--output-format", "stream-json", "--verbose",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    finally:
        os.unlink(spfile)
    return parse_run(proc.stdout.splitlines())


def main(argv: list[str]) -> int:
    filters = [a.lower() for a in argv]
    selected = [s for s in SCENARIOS if not filters or any(f in s.name.lower() for f in filters)]
    ok = 0
    fail = 0
    for sc in selected:
        print(f"\n=== {sc.name} ===")
        print(f"  cliente: {sc.phone} | msg: {sc.message[:70]}")
        # R-09/M-08: tier roteado deterministicamente. Quando o cenario declara
        # expected_model, verificamos o roteamento ANTES de gastar o turno do LLM
        # (assert puro, sem subprocess) e o reusamos no spawn (--model).
        tier = rotear_modelo(sc.message, primeiro_turno=True)
        print(f"  modelo: {tier.value}", end="")
        model_ok = sc.expected_model is None or tier.value == sc.expected_model
        if not model_ok:
            print(f"  [FAIL roteamento: esperado {sc.expected_model}]")
            fail += 1
            continue
        print(" (esperado)" if sc.expected_model else "")
        # Setup por-cenario (R-03/J10b): monta a PRECONDICAO de estado ANTES de gastar
        # o turno do LLM (ex.: semeia `pagamento.confirmado` na memoria via REST). So
        # alguns cenarios definem. Falha de setup REPROVA o cenario (nao passa por
        # engano nem derruba a suite) — a precondicao indisponivel e um FAIL legitimo.
        if sc.setup is not None:
            try:
                sc.setup(sc.phone)
                print("  setup: ok (precondicao semeada)")
            except Exception as exc:  # noqa: BLE001 — falha de setup vira FAIL do cenario
                print(f"  FAIL  (setup falhou: {type(exc).__name__}: {exc})")
                fail += 1
                continue
        run = run_agent(sc.phone, sc.message, modelo=tier)
        passed, detail = sc.assertion(run)
        print(f"  tools: {run.tool_names()}")
        print(f"  resposta: {run.result[:160].replace(chr(10), ' ')}")
        if passed:
            ok += 1
            print(f"  PASS  ({detail})")
        else:
            fail += 1
            print(f"  FAIL  ({detail})")
    total = ok + fail
    score = compute_score(ok, total)
    threshold = gate_threshold()
    print(f"\nRESULTADO: {ok} PASS, {fail} FAIL")
    print(f"SCORE: {score}/100 (gate >= {threshold})")
    if not gate_passes(score, threshold):
        print(f"GATE: REPROVADO (score {score} < {threshold})")
        return 1
    print("GATE: APROVADO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
