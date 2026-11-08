"""RouteCompletion: admisión, modo efectivo, presupuesto, circuito, reintentos y telemetría."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeUpstream, FixedRandom, ManualClock, NoSleep, RecordingMetrics, RecordingTelemetry

from llm_gateway.adapters.outbound.kv import InMemoryKeyValue
from llm_gateway.application.budget_service import BudgetService
from llm_gateway.application.route_completion import RetryConfig, RouteCompletion
from llm_gateway.domain.budget import BudgetLimits, ModelPrice
from llm_gateway.domain.circuit import CircuitConfig
from llm_gateway.domain.routing import RoutingPolicy, TelemetrySampling

PRICE = ModelPrice(0.15, 0.60)
BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hola"}], "max_tokens": 100}


def make(
    *,
    global_mode: str = "live",
    key: bool = True,
    limit_usd: float = 3.0,
    rng: float = 0.5,
    telemetry: RecordingTelemetry | None = None,
    **limits: Any,
) -> tuple[RouteCompletion, FakeUpstream, RecordingMetrics, RecordingTelemetry, BudgetService]:
    upstream, metrics, tele = FakeUpstream(), RecordingMetrics(), telemetry or RecordingTelemetry()
    budget = BudgetService(InMemoryKeyValue(), BudgetLimits(limit_usd=limit_usd, **limits))
    uc = RouteCompletion(
        policy=RoutingPolicy(global_mode=global_mode, has_api_key=key, prices={"gpt-4o-mini": PRICE}),  # type: ignore[arg-type]
        budget=budget,
        upstream=upstream,
        metrics=metrics,
        telemetry=tele,
        sampling=TelemetrySampling(0.01),
        clock=ManualClock(),
        sleeper=NoSleep(),
        rng=FixedRandom(rng),
        circuit=CircuitConfig(threshold=3, window_s=30, open_s=30),
        retry=RetryConfig(retries=2),
    )
    return uc, upstream, metrics, tele, budget


def hdr(mode: str = "simulated", task: str = "t1", agent: str = "orchestrator") -> dict[str, str]:
    return {
        "X-Task-Mode": mode,
        "X-Task-Id": task,
        "X-Agent": agent,
        "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
    }


async def test_public_traffic_is_always_simulated_and_spends_nothing() -> None:
    uc, up, metrics, _, budget = make()
    res = await uc(BODY, hdr("simulated"))
    assert res.status == 200
    assert res.body["x_gateway"] == {"mode": "simulated", "degraded": False, "reason": None}
    assert up.count("openai") == 0 and metrics.live_tokens() == 0
    assert await budget.remaining_usd() == 3.0
    # traceparent y X-Agent viajan a fake-llm
    assert up.calls[0][2]["traceparent"].startswith("00-") and up.calls[0][2]["X-Agent"] == "orchestrator"


async def test_live_goes_to_openai_and_reconciles_actual_cost() -> None:
    uc, up, metrics, _, budget = make()
    res = await uc(BODY, hdr("live"))
    assert res.status == 200 and res.body["x_gateway"]["mode"] == "live"
    assert res.headers["X-LLM-Mode"] == "live" and up.count("openai") == 1
    expected = 3.0 - PRICE.cost_micro(100, 50) / 1e6  # usage del upstream: 100 in / 50 out
    assert await budget.remaining_usd() == pytest.approx(expected)
    assert metrics.live_tokens() == 150 and metrics.remaining == pytest.approx(expected)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"global_mode": "simulated"}, "global_simulated"),
        ({"key": False}, "no_api_key"),
        ({"limit_usd": 0.0}, "budget_exhausted"),
    ],
)
async def test_live_degrades_to_fake(kwargs: dict[str, Any], reason: str) -> None:
    uc, up, metrics, _, _ = make(**kwargs)
    res = await uc(BODY, hdr("live"))
    assert res.status == 200
    assert res.body["x_gateway"] == {"mode": "simulated", "degraded": True, "reason": reason}
    assert res.headers["X-LLM-Degraded"] == "true" and res.headers["X-LLM-Reason"] == reason
    assert up.count("openai") == 0 and metrics.live_tokens() == 0


async def test_openai_failure_degrades_and_releases_reservation() -> None:
    uc, up, _, _, budget = make()
    up.fail["openai"] = [500, 502, 503]
    res = await uc(BODY, hdr("live"))
    assert res.body["x_gateway"]["reason"] == "upstream_error" and res.body["x_gateway"]["degraded"]
    assert up.count("openai") == 3  # 1 intento + 2 reintentos
    assert await budget.remaining_usd() == 3.0


async def test_circuit_opens_and_short_circuits_live() -> None:
    uc, up, metrics, _, _ = make()
    up.fail["openai"] = [500] * 3
    await uc(BODY, hdr("live", task="a"))
    assert uc.circuits["openai"].state.name == "OPEN" and int(metrics.circuits["openai"]) == 2
    res = await uc(BODY, hdr("live", task="b"))
    assert res.body["x_gateway"]["reason"] == "circuit_open" and up.count("openai") == 3


async def test_contract_errors_are_not_retried_nor_counted_by_circuit() -> None:
    uc, up, _, _, _ = make()
    up.fail["openai"] = [400]
    res = await uc(BODY, hdr("live"))
    assert res.body["x_gateway"]["reason"] == "upstream_error" and up.count("openai") == 1
    assert uc.circuits["openai"].state.name == "CLOSED"


async def test_fake_failures_return_503_with_retry_after_and_open_circuit() -> None:
    uc, up, _, _, _ = make()
    up.fail["fake"] = [500] * 10
    res = await uc(BODY, hdr("simulated"))
    assert res.status == 503 and res.headers["Retry-After"] == "2"
    res = await uc(BODY, hdr("simulated"))
    assert res.status == 503 and res.body["error"]["code"] == "circuit_open"


async def test_per_task_step_limit_degrades_seventh_live_call() -> None:
    uc, _, _, _, _ = make()
    reasons = [(await uc(BODY, hdr("live", task="loop"))).body["x_gateway"]["reason"] for _ in range(7)]
    assert reasons == [None] * 6 + ["task_step_limit"]


async def test_live_tasks_per_minute_cap() -> None:
    uc, _, _, _, _ = make()
    modes = [(await uc(BODY, hdr("live", task=f"t{i}"))).body["x_gateway"] for i in range(6)]
    assert [m["mode"] for m in modes] == ["live"] * 5 + ["simulated"]
    assert modes[-1]["reason"] == "live_rate_limit"


async def test_rejections_are_openai_shaped() -> None:
    uc, up, _, _, _ = make()
    res = await uc({"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]}, hdr())
    assert res.status == 400 and set(res.body["error"]) == {"message", "type", "param", "code"}
    assert up.calls == []


async def test_telemetry_live_always_simulated_sampled() -> None:
    uc, _, _, tele, _ = make(rng=0.5)
    await uc(BODY, hdr("live"))
    await uc(BODY, hdr("simulated"))
    assert [r.mode for r in tele.records] == ["live"]
    rec = tele.records[0]
    assert rec.task_id == "t1" and rec.prompt_tokens == 100 and rec.cost_usd > 0
    uc2, _, _, tele2, _ = make(rng=0.001)
    await uc2(BODY, hdr("simulated"))
    assert [r.mode for r in tele2.records] == ["simulated"]


async def test_telemetry_failure_is_fail_open() -> None:
    uc, _, _, _, _ = make(telemetry=RecordingTelemetry(raise_on_record=True))
    res = await uc(BODY, hdr("live"))
    assert res.status == 200 and res.body["x_gateway"]["mode"] == "live"
