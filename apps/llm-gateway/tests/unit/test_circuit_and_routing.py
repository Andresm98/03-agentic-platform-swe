"""Circuit breaker y políticas de enrutado (puras)."""

from __future__ import annotations

import pytest
from fakes import ManualClock

from llm_gateway.domain.budget import ModelPrice
from llm_gateway.domain.circuit import CircuitBreaker, CircuitConfig, CircuitState
from llm_gateway.domain.routing import (
    RequestRejectedError,
    RoutingPolicy,
    TelemetrySampling,
    live_precondition,
    prepare,
)


def _breaker(clock: ManualClock, changes: list[CircuitState]) -> CircuitBreaker:
    return CircuitBreaker(
        "openai",
        CircuitConfig(threshold=3, window_s=10, open_s=30),
        clock.now,
        lambda _n, s: changes.append(s),
    )


def test_circuit_opens_after_threshold_within_window() -> None:
    clock, changes = ManualClock(), []
    cb = _breaker(clock, changes)
    cb.record_failure()
    clock.t += 20  # fuera de la ventana: el primer fallo caduca
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    cb.record_failure()
    assert cb.state == CircuitState.OPEN and not cb.allow()
    assert changes == [CircuitState.CLOSED, CircuitState.OPEN]


def test_half_open_single_probe_then_close_or_reopen() -> None:
    clock, changes = ManualClock(), []
    cb = _breaker(clock, changes)
    for _ in range(3):
        cb.record_failure()
    clock.t += 31
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.allow() and not cb.allow()  # una sola sonda
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    clock.t += 31
    assert cb.allow()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED and cb.allow()


POLICY = RoutingPolicy(prices={"gpt-4o-mini": ModelPrice(0.15, 0.6)}, max_input_tokens=200)


def _body(**kw: object) -> dict[str, object]:
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hola"}], **kw}


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"model": "gpt-4o", "messages": [{"role": "user", "content": "x"}]}, "model_not_allowed"),
        (_body(stream=True), "stream_unsupported"),
        (_body(messages=[]), "missing_messages"),
        (_body(messages=[{"role": "user", "content": "x" * 2000}]), "context_length_exceeded"),
        (_body(max_tokens=0), "invalid_max_tokens"),
        ([], "invalid_body"),
    ],
)
def test_prepare_rejects(body: object, code: str) -> None:
    with pytest.raises(RequestRejectedError) as exc:
        prepare(body, "researcher", POLICY)
    assert exc.value.code == code and exc.value.status == 400


def test_prepare_clamps_max_tokens_per_agent_and_drops_fields() -> None:
    req = prepare(_body(max_tokens=5000, n=3, user="u", max_completion_tokens=10), "orchestrator", POLICY)
    assert req.max_tokens == 300 and req.body["max_tokens"] == 300
    assert "n" not in req.body and "user" not in req.body and "max_completion_tokens" not in req.body
    assert prepare(_body(), "executor", POLICY).max_tokens == 200
    assert prepare(_body(max_tokens=50), "executor", POLICY).max_tokens == 50


def test_live_preconditions_order() -> None:
    live_key = RoutingPolicy(global_mode="live", has_api_key=True)
    assert live_precondition(live_key, False, "t") == "not_requested"
    assert (
        live_precondition(RoutingPolicy(global_mode="simulated", has_api_key=True), True, "t")
        == "global_simulated"
    )
    assert live_precondition(RoutingPolicy(global_mode="live"), True, "t") == "no_api_key"
    assert live_precondition(live_key, True, "") == "missing_task_id"
    assert live_precondition(live_key, True, "t") is None


def test_telemetry_sampling_live_always_simulated_by_rate() -> None:
    s = TelemetrySampling(simulated_rate=0.01)
    assert s.should_export("live", 0.99)
    assert s.should_export("simulated", 0.005)
    assert not s.should_export("simulated", 0.5)
    assert not TelemetrySampling(0.0).should_export("simulated", 0.0)
