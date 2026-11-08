"""API pública del orquestador: `POST /tasks` (202 + task_id) y `GET /tasks/{id}`.

- Validación estricta del payload (campos extra prohibidos) y tamaño máximo del cuerpo (413).
- `X-Demo-Token` se pasa al caso de uso; nunca se registra ni se devuelve.
- Backpressure → 429/503 con `Retry-After`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agentlib.adapters.outbound.otel import inject_traceparent
from agentlib.domain.errors import TransientDependencyError
from agentlib.domain.ids import is_uuid
from orchestrator.application.tasks import GetTask, SubmitTask, TaskShedError
from orchestrator.domain.task import MAX_GOAL_CHARS, InvalidTaskError, TaskSpec


class TaskCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    goal: str = Field(min_length=1, max_length=MAX_GOAL_CHARS)
    complexity: int = Field(default=3, ge=1, le=10)


def _problem(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def register_routes(app: FastAPI, submit: SubmitTask, get_task: GetTask, max_body_bytes: int) -> None:
    @app.post("/tasks")
    async def create_task(request: Request) -> JSONResponse:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_body_bytes:
            return _problem(413, "payload_too_large", f"body must be at most {max_body_bytes} bytes")
        raw = await request.body()
        if len(raw) > max_body_bytes:
            return _problem(413, "payload_too_large", f"body must be at most {max_body_bytes} bytes")
        try:
            dto = TaskCreateDTO.model_validate_json(raw or b"{}")
            spec = TaskSpec(dto.goal, dto.complexity)
        except (ValidationError, InvalidTaskError) as exc:
            return _problem(422, "invalid_task", str(exc).splitlines()[0][:300])
        try:
            accepted = await submit(spec, request.headers.get("x-demo-token"), inject_traceparent())
        except TaskShedError as exc:
            return _problem(
                exc.status,
                exc.reason,
                "the platform is saturated, retry later",
                {"Retry-After": str(exc.retry_after_s)},
            )
        body: dict[str, Any] = {"task_id": accepted.task_id, "mode": accepted.mode, "status": "accepted"}
        return JSONResponse(body, status_code=202, headers={"Location": f"/tasks/{accepted.task_id}"})

    @app.get("/tasks/{task_id}")
    async def read_task(task_id: str) -> JSONResponse:
        if not is_uuid(task_id):
            return _problem(404, "not_found", "unknown task")
        try:
            view = await get_task(task_id)
        except TransientDependencyError:
            return _problem(503, "workflow_unavailable", "state store unavailable", {"Retry-After": "2"})
        if view is None:
            return _problem(404, "not_found", "unknown task")
        return JSONResponse(view)
