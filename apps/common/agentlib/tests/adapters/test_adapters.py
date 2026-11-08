"""Adaptadores comunes: Dapr pub/sub (HTTP simulado), cliente OpenAI→gateway, HTTP app, logs."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from agentlib.adapters.inbound.dapr_subscription import unwrap_cloudevent
from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.adapters.outbound.json_logging import JsonFormatter, bind_task
from agentlib.adapters.outbound.openai_llm import OpenAIGatewayLLM
from agentlib.adapters.outbound.otel import OtelTracer, inject_traceparent, setup_tracing
from agentlib.adapters.outbound.system import SystemClock, Uuid7Generator
from agentlib.application.handle_request import WorkOutput
from agentlib.bootstrap.runtime import build_worker_app, init_observability
from agentlib.bootstrap.settings import BaseSettings, env_bool, env_float, env_int, env_json
from agentlib.domain.chat import ChatRequest, ToolSpec
from agentlib.domain.errors import PublishRejectedError, TransientDependencyError
from agentlib.domain.messages import AgentRequest


async def test_dapr_publish_uses_cloudevent_id_and_traceparent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("healthz/outbound"):
            return httpx.Response(204)
        return httpx.Response(204 if "ok" in request.url.path else 500, text="stream full")

    pub = DaprPubSubPublisher(
        "http://127.0.0.1:3500/", "pubsub", httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await pub.publish("ok.topic", {"a": 1}, msg_id="t:0:ok.topic", traceparent="tp")
    req = seen[0]
    assert req.url.path == "/v1.0/publish/pubsub/ok.topic"
    assert req.url.params["metadata.cloudevent.id"] == "t:0:ok.topic" and req.headers["traceparent"] == "tp"
    assert json.loads(req.content) == {"a": 1}
    with pytest.raises(PublishRejectedError):
        await pub.publish("bad", {}, msg_id="x")
    assert await pub.healthy()
    await pub.aclose()


async def test_dapr_publish_transport_error_and_unhealthy() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no sidecar")

    pub = DaprPubSubPublisher("http://x", "pubsub", httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    with pytest.raises(PublishRejectedError):
        await pub.publish("t", {}, msg_id="m")
    assert not await pub.healthy()


def _gateway_client(handler: Any) -> AsyncOpenAI:
    async def ahandler(request: httpx2.Request) -> httpx2.Response:
        return handler(request)

    return AsyncOpenAI(
        base_url="http://gw/v1",
        api_key="x",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(ahandler)),
    )


async def test_openai_adapter_sends_control_headers_and_parses_gateway_extra() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        body = {
            "id": "c",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "k",
                                "type": "function",
                                "function": {"name": "f", "arguments": '{"a": 1}'},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            "x_gateway": {"mode": "simulated", "degraded": True, "reason": "global_simulated"},
        }
        return httpx2.Response(200, json=body)

    llm = OpenAIGatewayLLM(
        agent="researcher",
        base_url="http://gw/v1",
        model="gpt-4o-mini",
        max_tokens=200,
        client=_gateway_client(handler),
    )
    res = await llm.complete(
        ChatRequest([{"role": "user", "content": "hi"}], "t1", "live", (ToolSpec("f", "d", {}, ()),), "tp")
    )
    h = seen[0].headers
    assert (
        h["x-agent"] == "researcher"
        and h["x-task-id"] == "t1"
        and h["x-task-mode"] == "live"
        and h["traceparent"] == "tp"
    )
    sent = json.loads(seen[0].content)
    assert sent["max_tokens"] == 200 and sent["tools"][0]["function"]["name"] == "f"
    assert res.tool_calls[0].arguments == {"a": 1} and res.degraded and res.reason == "global_simulated"
    assert res.prompt_tokens == 7 and res.message["tool_calls"][0]["id"] == "k"


async def test_openai_adapter_maps_5xx_to_transient() -> None:
    llm = OpenAIGatewayLLM(
        agent="a",
        base_url="http://gw/v1",
        model="m",
        max_tokens=1,
        client=_gateway_client(lambda r: httpx2.Response(503, json={"error": {}})),
    )
    with pytest.raises(TransientDependencyError):
        await llm.complete(ChatRequest([{"role": "user", "content": "hi"}], "t", "simulated"))


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None:
        self.sent.append((topic, data))

    async def healthy(self) -> bool:
        return True


def test_worker_app_subscription_probes_and_event_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POD_NAME", "pod-a")
    settings = BaseSettings()

    async def work(req: AgentRequest) -> WorkOutput:
        return WorkOutput({"echo": req.goal})

    pub = FakePublisher()
    wa = build_worker_app(
        settings, role="research", work=work, metrics=init_observability(settings), publisher=pub
    )  # type: ignore[arg-type]
    with TestClient(wa.app) as c:
        subs = c.get("/dapr/subscribe").json()
        assert subs == [
            {
                "pubsubname": "pubsub",
                "topic": "agent.research.requested",
                "route": "/events/requested",
                "deadLetterTopic": "tasks.dead",
            }
        ]
        ce = {
            "specversion": "1.0",
            "data": {"task_id": "t", "step": 0, "role": "research", "goal": "hola"},
            "traceparent": "tp",
        }
        r = c.post("/events/requested", json=ce)
        assert r.json() == {"status": "SUCCESS"} and r.headers["X-Pod-Name"] == "pod-a"
        assert pub.sent[0][1]["result"] == {"echo": "hola"}
        assert c.post("/events/requested", content=b"nope").json() == {"status": "DROP"}
        assert c.get("/healthz").status_code == 200 and c.get("/readyz").json()["checks"] == {"dapr": True}
        assert 'tasks_processed_total{agent="agent",status="ok"} 1.0' in c.get("/metrics").text


def test_readiness_fails_closed_and_unwrap() -> None:
    settings = BaseSettings()

    async def broken() -> bool:
        raise RuntimeError

    async def work(req: AgentRequest) -> WorkOutput:
        return WorkOutput({})

    wa = build_worker_app(
        settings, role="analysis", work=work, metrics=init_observability(settings), publisher=FakePublisher()
    )  # type: ignore[arg-type]
    wa.readiness.add("broken", broken)
    with TestClient(wa.app) as c:
        assert c.get("/readyz").status_code == 503
    assert unwrap_cloudevent({"data": '{"a": 1}'}) == ({"a": 1}, None)
    assert unwrap_cloudevent({"data": "raw"}) == ({"raw": "raw"}, None)
    assert unwrap_cloudevent([1]) == ([1], None)


def test_json_logging_includes_task_id_and_redacts() -> None:
    fmt = JsonFormatter("svc")
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "hello %s", ("w",), None)
    rec.password = "s3cret"  # type: ignore[attr-defined]
    with bind_task("t-1"):
        out = json.loads(fmt.format(rec))
    assert (
        out["task_id"] == "t-1"
        and out["msg"] == "hello w"
        and out["password"] == "[REDACTED]"
        and out["service"] == "svc"
    )
    assert json.loads(fmt.format(rec))["task_id"] is None


def test_settings_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_INT", "7")
    monkeypatch.setenv("X_FLOAT", "0.5")
    monkeypatch.setenv("X_BOOL", "TRUE")
    monkeypatch.setenv("X_JSON", '{"a": 1}')
    monkeypatch.setenv("X_BADJSON", "[1]")
    assert env_int("X_INT", 1) == 7 and env_float("X_FLOAT", 1.0) == 0.5 and env_bool("X_BOOL", False)
    assert (
        env_int("MISSING", 3) == 3
        and env_json("X_JSON", {}) == {"a": 1}
        and env_json("MISSING", {"d": 1}) == {"d": 1}
    )
    with pytest.raises(ValueError):
        env_json("X_BADJSON", {})


def test_otel_noop_and_system_adapters() -> None:
    assert setup_tracing("svc", "http://x:4317", enabled=False) is False
    assert inject_traceparent() is None
    tp = "00-" + "1" * 32 + "-" + "2" * 16 + "-01"
    with OtelTracer("t").span("s", tp, {"k": 1}):
        pass
    assert SystemClock().now() > 0 and len(Uuid7Generator().new()) == 36
