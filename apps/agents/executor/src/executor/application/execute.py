"""Caso de uso Execute: el modelo elige la herramienta; el trabajo de CPU va a un proceso aparte."""

from __future__ import annotations

from typing import Any, Protocol

from agentlib.application.agent_loop import LoopConfig, run_agent_loop
from agentlib.application.handle_request import WorkOutput
from agentlib.application.ports import AgentMetricsPort, LLMPort
from agentlib.domain.chat import ChatRequest, ToolSpec
from agentlib.domain.messages import AgentRequest
from executor.domain.tools import CATALOG, UnknownToolError, clamp_complexity

TOOLS = (
    ToolSpec(
        "run_tool",
        "Run one deterministic CPU tool from the closed catalog.",
        {
            "name": {"type": "string", "enum": sorted(CATALOG)},
            "complexity": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        ("name", "complexity"),
    ),
)
SYSTEM = "You are the executor agent. Choose exactly one tool with run_tool."


class CpuRunnerPort(Protocol):
    """Ejecuta `run_tool` fuera del event loop (proceso aparte): /healthz sigue respondiendo."""

    async def run(self, name: str, complexity: int) -> dict[str, Any]: ...


class Execute:
    def __init__(
        self, llm: LLMPort, metrics: AgentMetricsPort, runner: CpuRunnerPort, max_llm_calls: int = 1
    ) -> None:
        self._llm, self._metrics, self._runner, self._max = llm, metrics, runner, max_llm_calls

    async def __call__(self, req: AgentRequest) -> WorkOutput:
        messages = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": f"{req.goal}\ncomplexity={req.complexity}\n{req.args.get('instructions', '')}",
            },
        ]

        async def run_tool(name: str, complexity: int = req.complexity) -> dict[str, Any]:
            if name not in CATALOG:
                raise UnknownToolError(name)
            # El modelo no puede pedir más complejidad que la admitida para la tarea.
            return await self._runner.run(name, min(clamp_complexity(complexity), req.complexity))

        try:
            loop = await run_agent_loop(
                self._llm,
                self._metrics,
                ChatRequest(messages, req.task_id, req.mode, TOOLS, req.traceparent),
                {"run_tool": run_tool},
                LoopConfig(max_steps=self._max),
            )
        except UnknownToolError as exc:
            return WorkOutput({"error": str(exc)})
        if loop.tool_results:
            return WorkOutput(dict(loop.tool_results[-1]["result"]), loop.degraded, loop.steps)
        # Sin tool call: herramienta por defecto, para que la tarea siga teniendo trabajo real.
        return WorkOutput(await self._runner.run("prime_count", req.complexity), loop.degraded, loop.steps)
