"""Adaptador de entrada Dapr Workflow: registra el workflow y sus actividades en el runtime.

El workflow (`application.workflow.task_workflow`) es un generador de comandos; aquí cada
comando se traduce a la API real del SDK (verificada en dapr 1.19.0):
- `ctx.call_activity(name, input=, retry_policy=)` → `TaskFailedError` si agota reintentos;
- `ctx.wait_for_external_event(name, timeout=timedelta)` → `TimeoutError` si vence;
- `ctx.set_custom_status(str)`.
Cada resultado queda persistido en el historial (Redis): si el pod muere, otra réplica reanuda el
workflow por replay sin repetir las actividades ya completadas (ni las llamadas al modelo).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Generator
from datetime import timedelta
from typing import Any

from dapr.ext.workflow import (
    DaprWorkflowContext,
    RetryPolicy,
    TaskFailedError,
    WorkflowActivityContext,
    WorkflowRuntime,
)

from agentlib.adapters.outbound.json_logging import bind_task
from orchestrator.application.workflow import (
    COMPLETE,
    DECIDE,
    DISPATCH,
    WORKFLOW_NAME,
    ActivityFailedError,
    CallActivity,
    SetStatus,
    StepTimeoutError,
    WaitEvent,
    task_workflow,
)

Activity = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def default_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        first_retry_interval=timedelta(seconds=1),
        max_number_of_attempts=4,
        backoff_coefficient=2.0,
        max_retry_interval=timedelta(seconds=15),
    )


def make_workflow(
    step_timeout_s: float, retry: RetryPolicy
) -> Callable[[DaprWorkflowContext, Any], Generator[Any, Any, Any]]:
    def run(ctx: DaprWorkflowContext, inp: Any) -> Generator[Any, Any, Any]:
        gen = task_workflow(inp, step_timeout_s)
        to_send: Any = None
        to_throw: BaseException | None = None
        while True:
            try:
                cmd = gen.throw(to_throw) if to_throw is not None else gen.send(to_send)
            except StopIteration as stop:
                return stop.value
            to_send, to_throw = None, None
            if isinstance(cmd, CallActivity):
                try:
                    to_send = yield ctx.call_activity(cmd.name, input=cmd.input, retry_policy=retry)
                except TaskFailedError as exc:
                    to_throw = ActivityFailedError(str(exc))
            elif isinstance(cmd, WaitEvent):
                try:
                    to_send = yield ctx.wait_for_external_event(
                        cmd.name, timeout=timedelta(seconds=cmd.timeout_s)
                    )
                except TimeoutError:
                    to_throw = StepTimeoutError(cmd.name)
            elif isinstance(cmd, SetStatus):
                ctx.set_custom_status(json.dumps(cmd.status))

    return run


def _activity(use_case: Activity) -> Callable[[WorkflowActivityContext, Any], Awaitable[dict[str, Any]]]:
    async def act(ctx: WorkflowActivityContext, inp: Any) -> dict[str, Any]:
        with bind_task(ctx.workflow_id):
            return await use_case(inp)

    return act


def register(
    runtime: WorkflowRuntime,
    *,
    decide: Activity,
    dispatch: Activity,
    complete: Activity,
    step_timeout_s: float,
    retry: RetryPolicy | None = None,
) -> None:
    runtime.register_workflow(
        make_workflow(step_timeout_s, retry or default_retry_policy()), name=WORKFLOW_NAME
    )
    runtime.register_activity(_activity(decide), name=DECIDE)
    runtime.register_activity(_activity(dispatch), name=DISPATCH)
    runtime.register_activity(_activity(complete), name=COMPLETE)
