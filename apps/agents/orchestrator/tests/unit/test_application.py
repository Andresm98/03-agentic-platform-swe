"""Casos de uso y workflow del orquestador, ejecutados de punta a punta con fakes en memoria."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from orch_fakes import Clock, Engine, Ids, Metrics, PlanLLM, Publisher, Queue

from agentlib.application.handle_request import Outcome
from orchestrator.application.activities import (
    CompleteTask,
    DecideNextStep,
    DispatchToAgent,
    HandleAgentResult,
)
from orchestrator.application.ports import WorkflowSnapshot
from orchestrator.application.tasks import GetTask, SubmitTask, TaskShedError
from orchestrator.application.workflow import (
    COMPLETE,
    DECIDE,
    DISPATCH,
    ActivityFailedError,
    CallActivity,
    SetStatus,
    StepTimeoutError,
    WaitEvent,
    task_workflow,
)
from orchestrator.domain.task import AdmissionPolicy, ShedPolicy, TaskSpec


def submit(
    queue: Queue | None = None,
    pub: Publisher | None = None,
    engine: Engine | None = None,
    m: Metrics | None = None,
) -> SubmitTask:
    return SubmitTask(
        admission=AdmissionPolicy("demo-token"),
        shed=ShedPolicy(threshold=100, retry_after_s=5),
        queue=queue or Queue(),
        publisher=pub or Publisher(),
        engine=engine or Engine(),
        ids=Ids(),
        clock=Clock(),
        metrics=m or Metrics(),
    )


async def test_submit_publishes_created_and_schedules_workflow() -> None:
    pub, engine, m = Publisher(), Engine(), Metrics()
    acc = await submit(pub=pub, engine=engine, m=m)(TaskSpec("goal", 2), "demo-token", "tp")
    assert acc.mode == "live"
    topic, data, msg_id = pub.sent[0]
    assert topic == "tasks.created" and msg_id == acc.task_id and data["traceparent"] == "tp"
    assert engine.scheduled[acc.task_id]["mode"] == "live" and engine.scheduled[acc.task_id]["max_steps"] == 6
    assert m.admissions == [("live", "valid")]


async def test_fake_token_is_simulated() -> None:
    acc = await submit()(TaskSpec("goal"), "fake", None)
    assert acc.mode == "simulated"


@pytest.mark.parametrize(
    ("kwargs", "reason", "status"),
    [
        ({"queue": Queue(150)}, "queue_full", 429),
        ({"pub": Publisher(fail=True)}, "stream_full", 503),
        ({"engine": Engine(fail=True)}, "workflow_unavailable", 503),
    ],
)
async def test_backpressure(kwargs: dict[str, Any], reason: str, status: int) -> None:
    m = Metrics()
    with pytest.raises(TaskShedError) as exc:
        await submit(m=m, **kwargs)(TaskSpec("goal"), None, None)
    assert exc.value.reason == reason and exc.value.status == status and exc.value.retry_after_s > 0
    assert m.shed_reasons == [reason]


async def test_get_task_views() -> None:
    engine = Engine()
    engine.snapshots["a"] = WorkflowSnapshot(
        "a", "running", {"steps": 2, "mode": "live", "degraded": True}, None, {"mode": "live"}
    )
    engine.snapshots["b"] = WorkflowSnapshot(
        "b", "completed", None, {"status": "completed", "summary": "s"}, None
    )
    get = GetTask(engine)
    assert await get("a") == {
        "task_id": "a",
        "status": "running",
        "mode": "live",
        "steps": 2,
        "degraded": True,
    }
    assert (await get("b"))["summary"] == "s"
    assert await get("zzz") is None


async def test_handle_agent_result_raises_event() -> None:
    engine = Engine()
    payload = {"task_id": "t", "step": 1, "role": "execution", "agent": "executor"}
    assert await HandleAgentResult(engine)(payload, None) is Outcome.SUCCESS
    assert engine.events[0][:2] == ("t", "agent_result_1")
    assert await HandleAgentResult(engine)({"bad": 1}, None) is Outcome.DROP
    assert await HandleAgentResult(Engine(fail=True))(payload, None) is Outcome.RETRY


def drive(
    gen: Generator[Any, Any, dict[str, Any]],
    llm: PlanLLM,
    pub: Publisher,
    *,
    timeout_steps: set[int] | None = None,
    fail: str | None = None,
) -> tuple[dict[str, Any], list[Any]]:
    """Simula el motor de workflows: ejecuta actividades con los casos de uso reales."""
    import asyncio

    m, clock = Metrics(), Clock(105.0)
    acts = {
        DECIDE: DecideNextStep(llm, m),
        DISPATCH: DispatchToAgent(pub),
        COMPLETE: CompleteTask(pub, clock, m),
    }
    log: list[Any] = []
    send: Any = None
    throw: BaseException | None = None
    while True:
        try:
            cmd = gen.throw(throw) if throw else gen.send(send)
        except StopIteration as stop:
            return stop.value, log
        send, throw = None, None
        log.append(cmd)
        if isinstance(cmd, CallActivity):
            if cmd.name == fail:
                throw = ActivityFailedError("boom")
                continue
            send = asyncio.run(acts[cmd.name](cmd.input))
        elif isinstance(cmd, WaitEvent):
            step = int(cmd.name.rsplit("_", 1)[1])
            if timeout_steps and step in timeout_steps:
                throw = StepTimeoutError(cmd.name)
            else:
                role = pub.sent[-1][1]["role"]
                send = {"status": "ok", "result": {"hits": 1}, "agent": role, "degraded": False}
        else:
            assert isinstance(cmd, SetStatus)


INPUT = {
    "task_id": "t1",
    "goal": "Analiza el escalado",
    "complexity": 3,
    "mode": "simulated",
    "created_at": 100.0,
    "traceparent": "tp",
}


def test_workflow_full_flow_decide_delegate_wait_finish() -> None:
    llm, pub = PlanLLM(), Publisher()
    out, log = drive(task_workflow(INPUT), llm, pub)
    assert out["status"] == "completed" and out["finish_reason"] == "finish"
    assert [s["role"] for s in out["steps"]] == ["research", "execution", "analysis"]
    topics = [t for t, _, _ in pub.sent]
    assert topics == [
        "agent.research.requested",
        "agent.execution.requested",
        "agent.analysis.requested",
        "tasks.completed",
    ]
    assert pub.sent[0][2] == "t1:0:agent.research.requested"  # id determinista
    assert len(llm.calls) == 4  # 4 decisiones del modelo
    assert all(c.traceparent == "tp" and c.task_id == "t1" for c in llm.calls)
    assert sum(isinstance(c, SetStatus) for c in log) == 3


def test_workflow_respects_max_steps() -> None:
    llm, pub = PlanLLM(plan=["dispatch_research"]), Publisher()
    out, _ = drive(task_workflow({**INPUT, "max_steps": 6}), llm, pub)
    assert out["finish_reason"] == "step_limit" and len(llm.calls) == 6 and len(out["steps"]) == 6


def test_workflow_step_timeout_is_recorded_and_continues() -> None:
    out, _ = drive(task_workflow(INPUT), PlanLLM(), Publisher(), timeout_steps={0})
    assert out["steps"][0]["status"] == "timeout" and out["status"] == "completed"


def test_workflow_activity_failure_marks_failed_and_still_completes() -> None:
    pub = Publisher()
    out, _ = drive(task_workflow(INPUT), PlanLLM(), pub, fail=DISPATCH)
    assert out["status"] == "failed" and pub.sent[-1][0] == "tasks.completed"


def test_degraded_decision_propagates() -> None:
    out, _ = drive(task_workflow(INPUT), PlanLLM(degraded=True), Publisher())
    assert out["degraded"] is True
