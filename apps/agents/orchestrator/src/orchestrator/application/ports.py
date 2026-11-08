"""Puertos del orquestador (además de los comunes de agentlib: LLM, publisher, reloj e ids)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkflowSnapshot:
    task_id: str
    status: str  # running | completed | failed | terminated | pending | suspended | unknown
    progress: dict[str, Any] | None
    output: dict[str, Any] | None
    input: dict[str, Any] | None


class WorkflowEnginePort(Protocol):
    """Motor de workflows durable (Dapr Workflow). Lanza `TransientDependencyError` si no responde."""

    async def schedule(self, task_id: str, payload: dict[str, Any]) -> None: ...

    async def get(self, task_id: str) -> WorkflowSnapshot | None: ...

    async def raise_event(self, task_id: str, name: str, data: dict[str, Any]) -> None: ...


class QueueProbePort(Protocol):
    """Profundidad actual del stream TASKS (None si no se puede medir: no se descarta nada)."""

    async def depth(self) -> int | None: ...


class OrchestratorMetricsPort(Protocol):
    def shed(self, reason: str) -> None: ...

    def admission(self, mode: str, token: str) -> None: ...

    def task_finished(self, mode: str, status: str, seconds: float) -> None: ...

    def agent_step(self, agent: str) -> None: ...
