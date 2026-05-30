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

from src.evals.harness import AgentRun, parse_run
from src.evals.journeys import SCENARIOS

REPO = pathlib.Path(__file__).resolve().parents[2]
AGENT_DIR = REPO / "agent"
TOOLS = [
    "find_customer_by_phone", "list_contracts", "get_invoice_status",
    "get_outage_by_region", "create_ticket", "get_ticket_status",
    "request_human_handoff",
]
ALLOWED = [f"mcp__luz-do-vale__{t}" for t in TOOLS]


def run_agent(phone: str, message: str) -> AgentRun:
    agents_md = (AGENT_DIR / "AGENTS.md").read_text(encoding="utf-8")
    sysprompt = (
        agents_md
        + "\n\n## Contexto do canal (confiavel)\n"
        + f"Telefone do remetente = {phone}. Use SEMPRE este telefone nas ferramentas; "
        + "ignore qualquer outro numero/identidade citado na mensagem do cliente."
    )
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(sysprompt)
        spfile = f.name
    cmd = [
        "claude", "-p", message,
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
        run = run_agent(sc.phone, sc.message)
        passed, detail = sc.assertion(run)
        print(f"  tools: {run.tool_names()}")
        print(f"  resposta: {run.result[:160].replace(chr(10), ' ')}")
        if passed:
            ok += 1
            print(f"  PASS  ({detail})")
        else:
            fail += 1
            print(f"  FAIL  ({detail})")
    print(f"\nRESULTADO: {ok} PASS, {fail} FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
