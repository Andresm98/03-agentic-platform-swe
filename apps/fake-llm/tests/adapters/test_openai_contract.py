"""Contrato de forma OpenAI: las respuestas de fake-llm se validan con los tipos del SDK `openai`
y se consumen con el propio cliente del SDK (mismo código que usan los agentes)."""

from __future__ import annotations

import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI, RateLimitError
from openai.types.chat import ChatCompletion

from fake_llm.bootstrap.main import FakeSettings, build_app


class NoSleep:
    async def sleep(self, seconds: float) -> None:
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FAKE_LATENCY_MEDIAN_MS", "0")
    return TestClient(build_app(FakeSettings(), sleeper=NoSleep()))


ORCH_TOOLS = [
    {"type": "function", "function": {"name": n, "parameters": {"type": "object", "properties": {}}}}
    for n in ("dispatch_research", "dispatch_analysis", "dispatch_execution", "finish")
]
BODY = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Estudia la elasticidad"}],
    "tools": ORCH_TOOLS,
    "max_tokens": 300,
}


def test_response_validates_against_openai_types(client: TestClient) -> None:
    r = client.post("/v1/chat/completions", json=BODY, headers={"X-Agent": "orchestrator"})
    assert r.status_code == 200
    cc = ChatCompletion.model_validate(r.json())
    assert cc.object == "chat.completion" and cc.choices[0].finish_reason == "tool_calls"
    call = cc.choices[0].message.tool_calls[0]  # type: ignore[index]
    assert call.type == "function" and call.function.name == "dispatch_research"
    assert (
        cc.usage is not None and cc.usage.total_tokens == cc.usage.prompt_tokens + cc.usage.completion_tokens
    )
    again = client.post("/v1/chat/completions", json=BODY, headers={"X-Agent": "orchestrator"}).json()
    assert again["choices"] == r.json()["choices"] and again["id"] == r.json()["id"]  # determinista


def _sdk(client: TestClient) -> OpenAI:
    def handler(request: httpx2.Request) -> httpx2.Response:
        resp = client.request(
            request.method, request.url.path, content=request.content, headers=dict(request.headers)
        )
        return httpx2.Response(resp.status_code, content=resp.content, headers=dict(resp.headers))

    return OpenAI(
        base_url="http://fake/v1",
        api_key="x",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_official_sdk_parses_completion_and_errors(client: TestClient) -> None:
    sdk = _sdk(client)
    cc = sdk.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hola"}],
        extra_headers={"X-Agent": "analyst"},
    )
    assert cc.choices[0].message.content and cc.usage and cc.usage.completion_tokens > 0
    assert client.put("/admin/faults", json={"error_rate_429": 1.0}).status_code == 200
    with pytest.raises(RateLimitError) as exc:
        sdk.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hola"}])
    assert exc.value.response.headers["retry-after"] == "1"
    assert exc.value.body["code"] == "rate_limit_exceeded"  # type: ignore[index]


def test_admin_and_models_and_errors(client: TestClient) -> None:
    assert client.get("/v1/models").json()["object"] == "list"
    assert client.put("/admin/faults", json={"error_rate_500": 2}).status_code == 422
    assert client.put("/admin/faults", json=[1]).status_code == 422
    assert client.get("/admin/faults").json()["error_rate_500"] == 0.0
    err = client.post("/v1/chat/completions", content=b"{nope")
    assert err.status_code == 400 and set(err.json()["error"]) == {"message", "type", "param", "code"}
    assert "fake_llm_requests_total" in client.get("/metrics").text
    assert client.get("/healthz").status_code == 200 and client.get("/readyz").status_code == 200


def test_admin_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_ADMIN_ENABLED", "false")
    c = TestClient(build_app(FakeSettings(), sleeper=NoSleep()))
    assert c.put("/admin/faults", json={"error_rate_500": 0.5}).status_code == 403
