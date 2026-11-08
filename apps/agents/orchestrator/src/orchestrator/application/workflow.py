"""Workflow de una tarea como generador de comandos, independiente de Dapr.

decidir → delegar → esperar el evento, como máximo 6 decisiones. El adaptador de Dapr Workflow
traduce cada comando a `ctx.call_activity` / `ctx.wait_for_external_event` y devuelve el
resultado al generador; así la lógica es testeable sin sidecar y el adaptador solo traduce.
Determinista: no usa reloj, azar ni E/S (requisito del replay de Dapr Workflow).
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from agentlib.domain.messages import result_event_name
from orchestrator.domain.plan import Decision, TaskRun

WORKFLOW_NAME = "task_workflow"
DECIDE = "decide_next_step"
DISPATCH = "dispatch_to_agent"
COMPLETE = "complete_task"


@dataclass(frozen=True)
class CallActivity:
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class WaitEvent:
    name: str
    timeout_s: float


@dataclass(frozen=True)
class SetStatus:
    status: dict[str, Any]


Command = CallActivity | WaitEvent | SetStatus


class StepTimeoutError(Exception):
    """El agente no respondió dentro del tiempo del paso."""


class ActivityFailedError(Exception):
    """Una actividad agotó sus reintentos."""


def task_workflow(
    inp: dict[str, Any], step_timeout_s: float = 120.0
) -> Generator[Command, Any, dict[str, Any]]:
    run = TaskRun.start(inp)
    try:
        while not run.done:
            decision = yield CallActivity(DECIDE, run.decide_input())
            run.apply_decision(Decision.from_dict(decision))
            if run.done:
                break
            yield CallActivity(DISPATCH, run.dispatch_input())
            try:
                result = yield WaitEvent(result_event_name(run.step), step_timeout_s)
            except StepTimeoutError:
                result = None
            run.apply_result(result)
            yield SetStatus(run.progress())
    except ActivityFailedError as exc:
        run.fail(f"activity_failed: {str(exc)[:200]}")
    outcome = run.outcome()
    yield CallActivity(COMPLETE, outcome)
    return outcome
