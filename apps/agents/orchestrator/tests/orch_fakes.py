"""Dobles en memoria del orquestador."""

from __future__ import annotations

from typing import Any

from agentlib.domain.chat import ChatRequest, ChatResult, ToolCall
from agentlib.domain.errors import PublishRejectedError, TransientDependencyError
from orchestrator.application.ports import WorkflowSnapshot

PLAN = ["dispatch_research", "dispatch_execution", "dispatch_analysis", "finish"]


class PlanLLM:
    """Sigue el plan según cuántos resultados de herramienta hay en la conversación."""

    def __init__(self, degraded: bool = False, plan: list[str] | None = None) -> None:
        self.degraded = degraded
        self.plan = plan or PLAN
        self.calls: list[ChatRequest] = []

    @property
    def agent(self) -> str:
        return "orchestrator"

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls.append(request)
        n = sum(1 for m in request.messages if m.get("role") == "tool")
        name = self.plan[min(n, len(self.plan) - 1)]
        args = {"summary": "ok"} if name == "finish" else {"instructions": "go"}
        return ChatResult(None, (ToolCall(f"call_{n}", name, args),), degraded=self.degraded)


class Publisher:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, dict[str, Any], str]] = []
        self.fail = fail

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None:
        if self.fail:
            raise PublishRejectedError("stream full")
        self.sent.append((topic, data, msg_id))


class Engine:
    def __init__(self, fail: bool = False) -> None:
        self.scheduled: dict[str, dict[str, Any]] = {}
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self.snapshots: dict[str, WorkflowSnapshot] = {}
        self.fail = fail

    async def schedule(self, task_id: str, payload: dict[str, Any]) -> None:
        if self.fail:
            raise TransientDependencyError("sidecar down")
        self.scheduled[task_id] = payload

    async def get(self, task_id: str) -> WorkflowSnapshot | None:
        if self.fail:
            raise TransientDependencyError("sidecar down")
        return self.snapshots.get(task_id)

    async def raise_event(self, task_id: str, name: str, data: dict[str, Any]) -> None:
        if self.fail:
            raise TransientDependencyError("sidecar down")
        self.events.append((task_id, name, data))


class Queue:
    def __init__(self, depth: int | None = None) -> None:
        self.value = depth

    async def depth(self) -> int | None:
        return self.value


class Metrics:
    def __init__(self) -> None:
        self.shed_reasons: list[str] = []
        self.admissions: list[tuple[str, str]] = []
        self.finished: list[tuple[str, str, float]] = []
        self.steps = 0

    def shed(self, reason: str) -> None:
        self.shed_reasons.append(reason)

    def admission(self, mode: str, token: str) -> None:
        self.admissions.append((mode, token))

    def task_finished(self, mode: str, status: str, seconds: float) -> None:
        self.finished.append((mode, status, seconds))

    def agent_step(self, agent: str) -> None:
        self.steps += 1


class Clock:
    def __init__(self, t: float = 100.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t


class Ids:
    def __init__(self) -> None:
        self.n = 0

    def new(self) -> str:
        self.n += 1
        return f"0190a000-0000-7000-8000-{self.n:012d}"
