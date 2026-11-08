"""Adaptadores del orquestador: API HTTP, driver de Dapr Workflow, sonda NATS y motor de workflows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
from dapr.ext.workflow import TaskFailedError
from fastapi.testclient import TestClient
from orch_fakes import Engine, PlanLLM, Publisher, Queue

from orchestrator.adapters.inbound.dapr_workflow import default_retry_policy, make_workflow, register
from orchestrator.adapters.outbound.dapr_workflow_engine import DaprWorkflowEngine, _loads
from orchestrator.adapters.outbound.nats_queue_probe import NatsQueueProbe, stream_messages
from orchestrator.application.ports import WorkflowSnapshot
from orchestrator.bootstrap.main import OrchestratorSettings, Overrides, build_app


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Publisher, Engine, Queue]:
    monkeypatch.setenv("DEMO_TOKEN", "the-demo-token")
    monkeypatch.setenv("WORKFLOW_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("MAX_BODY_BYTES", "512")
    pub, engine, queue = Publisher(), Engine(), Queue()
    app = build_app(
        OrchestratorSettings(), Overrides(engine=engine, queue=queue, publisher=pub, llm=PlanLLM())
    )
    return TestClient(app), pub, engine, queue


def test_post_task_202_and_modes(api: tuple[TestClient, Publisher, Engine, Queue]) -> None:
    c, pub, engine, _ = api
    r = c.post("/tasks", json={"goal": "Analiza", "complexity": 2})
    assert (
        r.status_code == 202
        and r.json()["mode"] == "simulated"
        and r.headers["Location"].endswith(r.json()["task_id"])
    )
    assert (
        c.post("/tasks", json={"goal": "x"}, headers={"X-Demo-Token": "fake"}).json()["mode"] == "simulated"
    )
    assert (
        c.post("/tasks", json={"goal": "x"}, headers={"X-Demo-Token": "the-demo-token"}).json()["mode"]
        == "live"
    )
    assert len(engine.scheduled) == 3 and all(t == "tasks.created" for t, _, _ in pub.sent)
    metrics = c.get("/metrics").text
    assert 'task_admissions_total{mode="simulated",token="invalid"} 1.0' in metrics


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"goal": ""}, 422),
        ({"goal": "x", "mode": "live"}, 422),
        ({"goal": "x", "complexity": "9"}, 422),
        ({"goal": "x" * 600}, 413),
    ],
)
def test_post_task_validation(
    api: tuple[TestClient, Publisher, Engine, Queue], body: dict[str, Any], status: int
) -> None:
    assert api[0].post("/tasks", json=body).status_code == status


def test_post_task_backpressure_has_retry_after(api: tuple[TestClient, Publisher, Engine, Queue]) -> None:
    c, _, _, queue = api
    queue.value = 10_000
    r = c.post("/tasks", json={"goal": "x"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "5"
    assert 'tasks_shed_total{reason="queue_full"} 1.0' in c.get("/metrics").text


def test_get_task_and_subscription(api: tuple[TestClient, Publisher, Engine, Queue]) -> None:
    c, _, engine, _ = api
    tid = c.post("/tasks", json={"goal": "x"}).json()["task_id"]
    engine.snapshots[tid] = WorkflowSnapshot(
        tid, "completed", None, {"status": "completed", "degraded": False}, None
    )
    assert c.get(f"/tasks/{tid}").json()["status"] == "completed"
    assert c.get("/tasks/not-a-uuid").status_code == 404
    assert c.get("/tasks/0190a000-0000-7000-8000-000000000999").status_code == 404
    subs = c.get("/dapr/subscribe").json()
    assert subs[0]["topic"] == "agent.*.completed" and subs[0]["deadLetterTopic"] == "tasks.dead"
    ce = {"data": {"task_id": tid, "step": 0, "role": "research", "agent": "researcher"}}
    assert c.post("/events/agent-completed", json=ce).json() == {"status": "SUCCESS"}
    assert engine.events[0][1] == "agent_result_0"
    engine.fail = True
    assert c.get(f"/tasks/{tid}").status_code == 503
    assert c.get("/readyz").status_code == 200


class FakeCtx:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def call_activity(self, name: str, *, input: Any, retry_policy: Any) -> tuple[str, str, Any]:
        return ("act", name, input)

    def wait_for_external_event(self, name: str, *, timeout: timedelta) -> tuple[str, str, timedelta]:
        return ("evt", name, timeout)

    def set_custom_status(self, status: str) -> None:
        self.statuses.append(status)


def test_dapr_workflow_driver_translates_commands() -> None:
    ctx = FakeCtx()
    gen = make_workflow(30.0, default_retry_policy())(ctx, {"task_id": "t", "goal": "g"})  # type: ignore[arg-type]
    kind, name, inp = gen.send(None)
    assert (kind, name) == ("act", "decide_next_step") and inp["step"] == 0
    kind, name, _ = gen.send({"tool": "dispatch_research", "call_id": "c0", "args": {}})
    assert name == "dispatch_to_agent"
    kind, name, timeout = gen.send({"topic": "agent.research.requested"})
    assert (kind, name, timeout) == ("evt", "agent_result_0", timedelta(seconds=30))
    _, name, _ = gen.throw(TimeoutError())  # el evento no llega a tiempo
    assert name == "decide_next_step" and '"steps": 1' in ctx.statuses[0]
    failed = TaskFailedError.__new__(TaskFailedError)  # el SDK la construye desde un proto
    Exception.__init__(failed, "boom")
    _, name, _ = gen.throw(failed)  # la decisión agota reintentos
    assert name == "complete_task"
    with pytest.raises(StopIteration) as stop:
        gen.send({"published": True})
    assert stop.value.value["status"] == "failed"


def test_register_uses_sdk_runtime_api() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.names: list[str] = []

        def register_workflow(self, fn: Any, *, name: str) -> None:
            self.names.append(name)

        def register_activity(self, fn: Any, *, name: str) -> None:
            self.names.append(name)

    async def act(inp: dict[str, Any]) -> dict[str, Any]:
        return inp

    rt = Runtime()
    register(rt, decide=act, dispatch=act, complete=act, step_timeout_s=10)  # type: ignore[arg-type]
    assert rt.names == ["task_workflow", "decide_next_step", "dispatch_to_agent", "complete_task"]


async def test_queue_probe_reads_jsz_and_caches() -> None:
    calls = []
    jsz = {"account_details": [{"stream_detail": [{"name": "TASKS", "state": {"messages": 42}}]}]}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=jsz)

    t = [0.0]
    probe = NatsQueueProbe(
        "http://nats:8222",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=lambda: t[0],
    )
    assert await probe.depth() == 42 and await probe.depth() == 42 and len(calls) == 1
    assert calls[0].url.params["streams"] == "true"
    assert await NatsQueueProbe("").depth() is None
    assert stream_messages({"account_details": []}, "TASKS") is None


async def test_queue_probe_fails_open() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    probe = NatsQueueProbe("http://nats:8222", client=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    assert await probe.depth() is None


async def test_workflow_engine_maps_errors_and_state() -> None:
    class State:
        class runtime_status:
            name = "RUNNING"

        serialized_custom_status = '"{\\"steps\\": 2}"'
        serialized_output = None
        serialized_input = '{"mode": "live"}'

    class Client:
        async def schedule_new_workflow(self, name: str, *, input: Any, instance_id: str) -> str:
            raise RuntimeError("grpc down")

        async def get_workflow_state(self, task_id: str, *, fetch_payloads: bool) -> Any:
            return State() if task_id == "a" else None

        async def raise_workflow_event(self, task_id: str, name: str, *, data: Any) -> None:
            raise RuntimeError("grpc down")

    eng = DaprWorkflowEngine()
    eng._client = Client()
    snap = await eng.get("a")
    assert (
        snap is not None
        and snap.status == "running"
        and snap.progress == {"steps": 2}
        and snap.input == {"mode": "live"}
    )
    assert await eng.get("b") is None
    from agentlib.domain.errors import TransientDependencyError

    with pytest.raises(TransientDependencyError):
        await eng.schedule("a", {})
    with pytest.raises(TransientDependencyError):
        await eng.raise_event("a", "e", {})
    assert _loads("not json") is None and _loads("[1]") is None
