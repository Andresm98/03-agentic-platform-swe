"""Guiones deterministas por rol. Mismo input → misma respuesta (incluidos los tool calls).

El orquestador ejecuta exactamente el mismo código contra `fake-llm` que contra OpenAI: el guion
devuelve tool calls con la misma forma que la API real.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ORCHESTRATOR_PLAN = ["dispatch_research", "dispatch_execution", "dispatch_analysis", "finish"]
EXECUTOR_TOOLS = ["prime_count", "sha256_chain", "matrix_multiply", "fibonacci_mod", "sort_numbers"]
_WORD = re.compile(r"[a-záéíóúñü]{4,}", re.IGNORECASE)
_COMPLEXITY = re.compile(r"complexity\s*[=:]\s*(\d+)", re.IGNORECASE)


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _first_user(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return str(m["content"])
    return ""


def _tool_call(name: str, args: dict[str, Any], seed: str) -> dict[str, Any]:
    return {
        "id": "call_" + _digest(seed, name)[:24],
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, sort_keys=True)},
    }


def _offered(tools: list[dict[str, Any]] | None) -> set[str]:
    return {t.get("function", {}).get("name", "") for t in tools or []}


def respond(
    agent: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
) -> tuple[str | None, list[dict[str, Any]]]:
    """Devuelve (content, tool_calls) para el agente y la conversación dados."""
    goal = _first_user(messages).split(chr(10), 1)[0]
    seed = _digest(agent, json.dumps(messages, sort_keys=True, default=str))
    offered = _offered(tools)

    if agent == "orchestrator" and offered:
        done = sum(1 for m in messages if m.get("role") == "tool")
        name = ORCHESTRATOR_PLAN[min(done, len(ORCHESTRATOR_PLAN) - 1)]
        if name not in offered:
            name = "finish" if "finish" in offered else sorted(offered)[0]
        if name == "finish":
            args: dict[str, Any] = {"summary": f"Task completed after {done} delegated steps."}
        else:
            args = {"instructions": f"Handle '{goal[:80]}' (step {done})."}
        return None, [_tool_call(name, args, seed)]

    if agent == "researcher" and "lookup_knowledge" in offered:
        words = sorted(_WORD.findall(goal.lower()), key=lambda w: (-len(w), w))
        topic = words[0] if words else "platform"
        return None, [_tool_call("lookup_knowledge", {"topic": topic}, seed)]

    if agent == "executor" and "run_tool" in offered:
        m = _COMPLEXITY.search(json.dumps(messages))
        complexity = max(1, min(10, int(m.group(1)))) if m else 3
        name = EXECUTOR_TOOLS[int(_digest(goal), 16) % len(EXECUTOR_TOOLS)]
        return None, [_tool_call("run_tool", {"name": name, "complexity": complexity}, seed)]

    if agent == "analyst":
        return "Assessment: results are consistent with the goal; deterministic score attached.", []

    return f"[fake-llm:{agent or 'unknown'}] {goal[:120]}".strip(), []
