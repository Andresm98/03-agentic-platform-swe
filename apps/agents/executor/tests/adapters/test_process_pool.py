"""El trabajo de CPU corre en un proceso aparte y no bloquea el event loop."""

from __future__ import annotations

import asyncio
import time

from agent_fakes import Publisher, ToolLLM
from fastapi.testclient import TestClient

from executor.adapters.outbound.process_pool import ProcessPoolCpuRunner
from executor.bootstrap.main import build_app


async def test_process_pool_keeps_event_loop_free() -> None:
    runner = ProcessPoolCpuRunner(min_duration_ms=400)
    await runner.run("prime_count", 1)  # calienta el proceso hijo (spawn)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    start = time.perf_counter()
    result = await runner.run("sha256_chain", 1)
    elapsed = time.perf_counter() - start
    task.cancel()
    runner.shutdown()
    assert result["elapsed_ms"] >= 400 and elapsed >= 0.4
    assert ticks >= 15, f"event loop blocked: only {ticks} ticks"


def test_app_event_flow_with_fake_runner() -> None:
    class Runner:
        async def run(self, name: str, complexity: int) -> dict[str, object]:
            return {"tool": name, "complexity": complexity}

    pub = Publisher()
    llm = ToolLLM("run_tool", {"name": "fibonacci_mod", "complexity": 1})
    app = build_app(llm=llm, publisher=pub, runner=Runner())  # type: ignore[arg-type]
    with TestClient(app) as c:
        ce = {"data": {"task_id": "t", "step": 1, "role": "execution", "goal": "g"}}
        assert c.post("/events/requested", json=ce).json() == {"status": "SUCCESS"}
    assert pub.sent[0][0] == "agent.execution.completed"
    assert pub.sent[0][1]["result"]["tool"] == "fibonacci_mod"
