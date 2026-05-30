"""Nucleo (puro, testavel) do harness de evals do agente.

`parse_run` converte o stream-json do `claude -p` em um `AgentRun`; as assercoes
(journeys.py) operam sobre ele. Sem dependencia de LLM/subprocess -> 100% testavel.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

_MCP_PREFIX = "mcp__luz-do-vale__"


@dataclass(frozen=True)
class ToolCall:
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRun:
    calls: list[ToolCall]
    result: str
    is_error: bool

    def tool_names(self) -> list[str]:
        return [c.name for c in self.calls]

    def called(self, name: str) -> bool:
        return name in self.tool_names()

    def wrote_ticket(self) -> bool:
        return any(
            c.name == "create_ticket" and c.input.get("confirmar") is True for c in self.calls
        )

    def used_phone(self, phone: str) -> bool:
        return any(str(c.input.get("phone", "")) == phone for c in self.calls)


def parse_run(lines: Iterable[str]) -> AgentRun:
    calls: list[ToolCall] = []
    result = ""
    is_error = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "assistant":
            message = obj.get("message", {})
            content = message.get("content", []) if isinstance(message, dict) else []
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name", ""))
                if name.startswith(_MCP_PREFIX):
                    inp = block.get("input")
                    calls.append(
                        ToolCall(
                            name=name[len(_MCP_PREFIX) :],
                            input=dict(inp) if isinstance(inp, dict) else {},
                        )
                    )
        elif kind == "result":
            result = str(obj.get("result") or "")
            is_error = bool(obj.get("is_error"))
    return AgentRun(calls=calls, result=result, is_error=is_error)


def has_kw(text: str, *kws: str) -> bool:
    low = text.lower()
    return any(k in low for k in kws)
