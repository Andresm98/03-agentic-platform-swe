"""API HTTP del gateway extremo a extremo (composition root con KV en memoria y upstream falso)."""

from __future__ import annotations

import time

import httpx
import pytest
from fakes import FakeUpstream
from fastapi.testclient import TestClient

from llm_gateway.adapters.outbound.http_upstream import HttpUpstream
from llm_gateway.adapters.outbound.kv import InMemoryKeyValue, NatsKeyValue
from llm_gateway.application.ports import CasConflictError, UpstreamFailureError
from llm_gateway.bootstrap.main import build_app, make_telemetry
from llm_gateway.bootstrap.settings import GatewaySettings


def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> tuple[TestClient, FakeUpstream]:
    for k, v in {"LANGSMITH_ENABLED": "false", **env}.items():
        monkeypatch.setenv(k, v)
    up = FakeUpstream()
    app = build_app(GatewaySettings(), kv=InMemoryKeyValue(), upstream=up)
    return TestClient(app), up


def _wait_ready(c: TestClient) -> None:
    for _ in range(50):
        if c.get("/readyz").status_code == 200:
            return
        time.sleep(0.02)
    raise AssertionError("gateway never became ready")


BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hola"}]}


def test_chat_completion_contract_and_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = _client(monkeypatch)
    with c:
        _wait_ready(c)
        r = c.post(
            "/v1/chat/completions", json=BODY, headers={"X-Task-Mode": "live", "X-Agent": "researcher"}
        )
        assert (
            r.status_code == 200 and r.headers["X-LLM-Mode"] == "simulated"
        )  # LLM_GLOBAL_MODE=simulated por defecto
        assert r.json()["x_gateway"]["reason"] == "global_simulated"
        assert r.headers["X-Pod-Name"]
        metrics = c.get("/metrics").text
        assert 'llm_tokens_total{agent="researcher",direction="input",mode="simulated"}' in metrics
        assert 'llm_tokens_total{agent="researcher",direction="input",mode="live"}' not in metrics
        assert c.get("/v1/models").json()["data"][0]["id"] in {"gpt-4o-mini", "gpt-4.1-mini"}
        assert c.get("/budget").json()["remaining_usd"] == 3.0
        assert c.post("/v1/chat/completions", content=b"{bad").status_code == 400


def test_live_with_key_in_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    c, up = _client(monkeypatch, LLM_GLOBAL_MODE="live", OPENAI_API_KEY="sk-test-not-real")
    with c:
        _wait_ready(c)
        r = c.post("/v1/chat/completions", json=BODY, headers={"X-Task-Mode": "live", "X-Task-Id": "t1"})
        assert r.json()["x_gateway"]["mode"] == "live" and up.count("openai") == 1


def test_langsmith_disabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_ENABLED", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics

    assert type(make_telemetry(GatewaySettings(), FleetMetrics())).__name__ == "NoopTelemetry"
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    tele = make_telemetry(GatewaySettings(), FleetMetrics())
    assert type(tele).__name__ == "LangSmithTelemetry"
    tele.shutdown()  # type: ignore[attr-defined]


async def test_http_upstream_maps_errors_and_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "fake" in str(request.url):
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": []})

    up = HttpUpstream(
        openai_base_url="https://api.openai.test/v1",
        openai_api_key="sk-x",
        fake_base_url="http://fake/v1",
        timeout_s=1,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await up.chat("openai", {"model": "m"}, {"X-Agent": "a"}) == {"choices": []}
    assert seen[0].headers["authorization"] == "Bearer sk-x" and "x-agent" not in seen[0].headers
    with pytest.raises(UpstreamFailureError) as exc:
        await up.chat("fake", {"model": "m"}, {"X-Agent": "a"})
    assert exc.value.status == 429 and exc.value.retryable
    assert "authorization" not in seen[1].headers and seen[1].headers["x-agent"] == "a"
    await up.aclose()


async def test_nats_kv_adapter_maps_errors() -> None:
    from nats.js.errors import KeyNotFoundError, KeyWrongLastSequenceError

    class Entry:
        value = b"5"
        revision = 7

    class FakeNatsKV:
        async def get(self, key: str) -> Entry:
            if key == "missing":
                raise KeyNotFoundError
            return Entry()

        async def create(self, key: str, value: bytes) -> int:
            raise KeyWrongLastSequenceError

        async def update(self, key: str, value: bytes, last: int) -> int:
            return last + 1

    kv = NatsKeyValue(FakeNatsKV())
    assert await kv.get("missing") is None
    assert await kv.get("k") == (b"5", 7)
    assert await kv.update("k", b"6", last=7) == 8
    with pytest.raises(CasConflictError):
        await kv.create("k", b"1")
