"""Bucle de agente con tool calls y límite de pasos.

El modelo decide qué herramienta usar; el bucle solo ejecuta herramientas de un registro cerrado
(nunca código ni shell). Cada llamada al modelo es un paso. Con `summarize=False` el resultado de
la herramienta es la respuesta, sin una llamada extra: así una tarea cabe en 6 llamadas
(4 del orquestador + investigador + ejecución; el análisis es determinista).
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agentlib.application.ports import AgentMetricsPort, LLMPort
from agentlib.domain.chat import ChatRequest, Message, ToolCall, ToolSpec

ToolFn = Callable[..., Any] | Callable[..., Awaitable[Any]]


@dataclass
class LoopResult:
    final: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0
    degraded: bool = False
    stopped_by_limit: bool = False


@dataclass(frozen=True)
class LoopConfig:
    max_steps: int
    summarize: bool = False


async def _invoke(tools: Mapping[str, ToolFn], call: ToolCall) -> Any:
    fn = tools.get(call.name)
    if fn is None:
        return {"error": f"unknown tool '{call.name}'", "allowed": sorted(tools)}
    try:
        payload = fn(**call.arguments)
        return await payload if inspect.isawaitable(payload) else payload
    except (TypeError, ValueError) as exc:
        return {"error": f"invalid arguments: {exc}"}


async def run_agent_loop(
    llm: LLMPort,
    metrics: AgentMetricsPort,
    request: ChatRequest,
    tools: Mapping[str, ToolFn],
    config: LoopConfig,
) -> LoopResult:
    out = LoopResult()
    history: list[Message] = list(request.messages)
    for _ in range(config.max_steps):
        res = await llm.complete(
            ChatRequest(history, request.task_id, request.mode, request.tools, request.traceparent)
        )
        out.steps += 1
        out.degraded = out.degraded or res.degraded
        metrics.agent_step(llm.agent)
        if not res.tool_calls:
            out.final = res.content
            return out
        history.append(res.message)
        for call in res.tool_calls:
            payload = await _invoke(tools, call)
            out.tool_results.append({"tool": call.name, "arguments": call.arguments, "result": payload})
            history.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(payload, default=str)[:2000]}
            )
        if not config.summarize:
            return out
    out.stopped_by_limit = True
    return out


__all__ = ["LoopConfig", "LoopResult", "ToolFn", "ToolSpec", "run_agent_loop"]
