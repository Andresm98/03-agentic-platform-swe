"""Adaptador de `WorkflowEnginePort` con el cliente asíncrono de Dapr Workflow.

API verificada en `dapr` 1.19.0 (el workflow viene dentro del wheel principal desde 1.19; el
paquete `dapr-ext-workflow` es legado): `dapr.ext.workflow.aio.DaprWorkflowClient` con
`schedule_new_workflow(name, input=, instance_id=)`, `get_workflow_state(id, fetch_payloads=)` y
`raise_workflow_event(id, name, data=)`. El cliente gRPC se crea perezosamente dentro del event
loop de uvicorn (los canales `grpc.aio` quedan ligados al loop en el que se crean).
"""

from __future__ import annotations

import json
from typing import Any

from agentlib.domain.errors import TransientDependencyError
from orchestrator.application.ports import WorkflowSnapshot
from orchestrator.application.workflow import WORKFLOW_NAME


def _loads(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(value, str):  # el estado personalizado puede venir doblemente serializado
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


class DaprWorkflowEngine:
    def __init__(self, host: str | None = None, port: str | None = None) -> None:
        self._host, self._port = host, port
        self._client: Any = None

    def _c(self) -> Any:
        if self._client is None:
            from dapr.ext.workflow.aio import DaprWorkflowClient

            self._client = DaprWorkflowClient(host=self._host, port=self._port)
        return self._client

    async def schedule(self, task_id: str, payload: dict[str, Any]) -> None:
        try:
            await self._c().schedule_new_workflow(WORKFLOW_NAME, input=payload, instance_id=task_id)
        except Exception as exc:  # grpc.aio.AioRpcError y fallos de conexión
            raise TransientDependencyError(f"workflow schedule failed: {type(exc).__name__}") from exc

    async def get(self, task_id: str) -> WorkflowSnapshot | None:
        try:
            state = await self._c().get_workflow_state(task_id, fetch_payloads=True)
        except Exception as exc:
            raise TransientDependencyError(f"workflow state failed: {type(exc).__name__}") from exc
        if state is None:
            return None
        return WorkflowSnapshot(
            task_id=task_id,
            status=state.runtime_status.name.lower(),
            progress=_loads(state.serialized_custom_status),
            output=_loads(state.serialized_output),
            input=_loads(state.serialized_input),
        )

    async def raise_event(self, task_id: str, name: str, data: dict[str, Any]) -> None:
        try:
            await self._c().raise_workflow_event(task_id, name, data=data)
        except Exception as exc:
            raise TransientDependencyError(f"raise event failed: {type(exc).__name__}") from exc
