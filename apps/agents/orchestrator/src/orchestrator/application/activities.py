"""Casos de uso que ejecutan las actividades del workflow y el manejo de respuestas de agentes."""

from __future__ import annotations

from typing import Any

from agentlib.application.handle_request import Outcome
from agentlib.application.ports import ClockPort, EventPublisherPort, LLMPort
from agentlib.domain.chat import ChatRequest
from agentlib.domain.errors import InvalidMessageError, TransientDependencyError
from agentlib.domain.messages import AgentResult, message_id, requested_topic, result_event_name
from orchestrator.application.ports import OrchestratorMetricsPort, WorkflowEnginePort
from orchestrator.domain.plan import TOOLS, build_messages, decision_from_calls


class DecideNextStep:
    """Pregunta al modelo (vía gateway) cuál es la siguiente tool call."""

    def __init__(self, llm: LLMPort, metrics: OrchestratorMetricsPort) -> None:
        self._llm = llm
        self._metrics = metrics

    async def __call__(self, inp: dict[str, Any]) -> dict[str, Any]:
        messages = build_messages(inp["goal"], int(inp.get("complexity", 3)), inp.get("history") or [])
        res = await self._llm.complete(
            ChatRequest(messages, inp["task_id"], inp.get("mode", "simulated"), TOOLS, inp.get("traceparent"))
        )
        self._metrics.agent_step(self._llm.agent)
        calls = [(c.id, c.name, c.arguments) for c in res.tool_calls]
        return decision_from_calls(calls, res.content, res.degraded, int(inp.get("step", 0))).to_dict()


class DispatchToAgent:
    """Publica `agent.<rol>.requested` con id determinista (idempotente ante reintentos)."""

    def __init__(self, publisher: EventPublisherPort) -> None:
        self._publisher = publisher

    async def __call__(self, inp: dict[str, Any]) -> dict[str, Any]:
        topic = requested_topic(inp["role"])
        await self._publisher.publish(
            topic,
            inp,
            msg_id=message_id(inp["task_id"], int(inp["step"]), topic),
            traceparent=inp.get("traceparent"),
        )
        return {"topic": topic}


class CompleteTask:
    """Publica `tasks.completed` y registra la latencia de extremo a extremo."""

    def __init__(
        self, publisher: EventPublisherPort, clock: ClockPort, metrics: OrchestratorMetricsPort
    ) -> None:
        self._publisher = publisher
        self._clock = clock
        self._metrics = metrics

    async def __call__(self, outcome: dict[str, Any]) -> dict[str, Any]:
        await self._publisher.publish(
            "tasks.completed",
            outcome,
            msg_id=message_id(outcome["task_id"], 99, "tasks.completed"),
            traceparent=None,
        )
        elapsed = max(0.0, self._clock.now() - float(outcome.get("created_at") or self._clock.now()))
        self._metrics.task_finished(str(outcome.get("mode")), str(outcome.get("status")), elapsed)
        return {"published": True}


class HandleAgentResult:
    """`agent.*.completed` → evento externo del workflow `agent_result_<step>`."""

    def __init__(self, engine: WorkflowEnginePort) -> None:
        self._engine = engine

    async def __call__(self, payload: Any, traceparent: str | None) -> Outcome:
        try:
            result = AgentResult.from_dict(payload)
        except InvalidMessageError:
            return Outcome.DROP
        try:
            await self._engine.raise_event(result.task_id, result_event_name(result.step), result.to_dict())
        except TransientDependencyError:
            return Outcome.RETRY
        return Outcome.SUCCESS
