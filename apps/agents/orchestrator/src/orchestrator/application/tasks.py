"""Casos de uso de la API pública: SubmitTask (POST /tasks) y GetTask (GET /tasks/{id})."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentlib.application.ports import ClockPort, EventPublisherPort, IdGeneratorPort
from agentlib.domain.errors import PublishRejectedError, TransientDependencyError
from orchestrator.application.ports import OrchestratorMetricsPort, QueueProbePort, WorkflowEnginePort
from orchestrator.domain.plan import MAX_STEPS
from orchestrator.domain.task import AdmissionPolicy, Mode, ShedPolicy, TaskSpec


class TaskShedError(Exception):
    """La tarea no se acepta por backpressure (429/503 + Retry-After)."""

    def __init__(self, reason: str, status: int, retry_after_s: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class Accepted:
    task_id: str
    mode: Mode


class SubmitTask:
    def __init__(
        self,
        *,
        admission: AdmissionPolicy,
        shed: ShedPolicy,
        queue: QueueProbePort,
        publisher: EventPublisherPort,
        engine: WorkflowEnginePort,
        ids: IdGeneratorPort,
        clock: ClockPort,
        metrics: OrchestratorMetricsPort,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._admission, self._shed, self._queue = admission, shed, queue
        self._publisher, self._engine, self._ids, self._clock = publisher, engine, ids, clock
        self._metrics, self._max_steps = metrics, max_steps

    async def __call__(self, spec: TaskSpec, demo_token: str | None, traceparent: str | None) -> Accepted:
        decision = self._admission.decide(demo_token)
        self._metrics.admission(decision.mode, decision.token)
        if self._shed.should_shed(await self._queue.depth()):
            self._reject("queue_full", 429, self._shed.retry_after_s)
        task_id = self._ids.new()
        payload: dict[str, Any] = {
            "task_id": task_id,
            "goal": spec.goal,
            "complexity": spec.complexity,
            "mode": decision.mode,
            "created_at": self._clock.now(),
            "max_steps": self._max_steps,
            "traceparent": traceparent,
        }
        try:
            # task_id = Nats-Msg-Id: deduplicación; con el stream lleno (discard=new) falla aquí.
            await self._publisher.publish("tasks.created", payload, msg_id=task_id, traceparent=traceparent)
        except PublishRejectedError:
            self._reject("stream_full", 503, 10)
        try:
            await self._engine.schedule(task_id, payload)
        except TransientDependencyError:
            self._reject("workflow_unavailable", 503, 5)
        return Accepted(task_id, decision.mode)

    def _reject(self, reason: str, status: int, retry_after: int) -> None:
        self._metrics.shed(reason)
        raise TaskShedError(reason, status, retry_after)


class GetTask:
    def __init__(self, engine: WorkflowEnginePort) -> None:
        self._engine = engine

    async def __call__(self, task_id: str) -> dict[str, Any] | None:
        snap = await self._engine.get(task_id)
        if snap is None:
            return None
        base: dict[str, Any] = {"task_id": task_id, "status": snap.status}
        if snap.output:
            return {**base, **snap.output, "status": snap.output.get("status", snap.status)}
        inp = snap.input or {}
        progress = snap.progress or {}
        return {
            **base,
            "mode": progress.get("mode", inp.get("mode")),
            "steps": progress.get("steps", 0),
            "degraded": progress.get("degraded", False),
        }
