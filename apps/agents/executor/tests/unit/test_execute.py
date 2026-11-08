"""Ejecución: catálogo cerrado, acotación de complejidad y caso de uso con runner falso."""

from __future__ import annotations

from typing import Any

import pytest
from agent_fakes import Metrics, ToolLLM

from agentlib.domain.messages import AgentRequest
from executor.application.execute import Execute
from executor.domain.tools import CATALOG, UnknownToolError, clamp_complexity, run_tool

REQ = AgentRequest(task_id="t", step=1, role="execution", goal="g", complexity=2)


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_each_tool_is_deterministic(name: str) -> None:
    a, b = run_tool(name, 1), run_tool(name, 1)
    a.pop("elapsed_ms")
    b.pop("elapsed_ms")
    assert a == b and a["tool"] == name and a["complexity"] == 1


def test_catalog_is_closed_and_complexity_clamped() -> None:
    with pytest.raises(UnknownToolError):
        run_tool("os.system", 1)
    assert clamp_complexity(99) == 10 and clamp_complexity(-1) == 1 and clamp_complexity("x") == 3
    assert run_tool("prime_count", 1, min_duration_ms=5)["elapsed_ms"] >= 5


class Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def run(self, name: str, complexity: int) -> dict[str, Any]:
        self.calls.append((name, complexity))
        return {"tool": name}


async def test_model_cannot_exceed_task_complexity() -> None:
    runner = Runner()
    llm = ToolLLM("run_tool", {"name": "sha256_chain", "complexity": 10})
    out = await Execute(llm, Metrics(), runner)(REQ)
    assert runner.calls == [("sha256_chain", 2)]
    assert out.result == {"tool": "sha256_chain"} and out.llm_calls == 1


async def test_unknown_tool_is_reported_without_running_anything() -> None:
    runner = Runner()
    out = await Execute(ToolLLM("run_tool", {"name": "shell", "complexity": 1}), Metrics(), runner)(REQ)
    assert runner.calls == [] and "error" in out.result


async def test_no_tool_call_runs_default_work() -> None:
    runner = Runner()
    await Execute(ToolLLM(None), Metrics(), runner)(REQ)
    assert runner.calls == [("prime_count", 2)]
