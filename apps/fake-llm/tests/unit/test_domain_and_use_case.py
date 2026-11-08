"""fake-llm: guiones deterministas, fallos, latencia lognormal y caso de uso (sin red)."""

from __future__ import annotations

import json
import math

import pytest

from fake_llm.application.complete_chat import CompleteChat, FaultControl
from fake_llm.domain.completion import ChatValidationError, completion, validate
from fake_llm.domain.faults import Fault, FaultProfile, latency_ms, pick_fault
from fake_llm.domain.scripts import EXECUTOR_TOOLS, ORCHESTRATOR_PLAN, respond

TOOLS = {
    name: [{"type": "function", "function": {"name": t}} for t in tools]
    for name, tools in {
        "orchestrator": ["dispatch_research", "dispatch_analysis", "dispatch_execution", "finish"],
        "researcher": ["lookup_knowledge"],
        "executor": ["run_tool"],
    }.items()
}


def test_orchestrator_script_follows_plan_by_tool_results() -> None:
    msgs: list[dict[str, object]] = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "Analiza el escalado"},
    ]
    seen = []
    for _ in range(5):
        _, calls = respond("orchestrator", msgs, TOOLS["orchestrator"])
        name = calls[0]["function"]["name"]
        seen.append(name)
        msgs += [
            {"role": "assistant", "tool_calls": calls},
            {"role": "tool", "tool_call_id": calls[0]["id"], "content": "{}"},
        ]
    assert seen[:4] == ORCHESTRATOR_PLAN and seen[4] == "finish"


def test_scripts_are_deterministic_and_role_specific() -> None:
    msgs = [{"role": "user", "content": "Investiga autoscaling y resiliencia complexity=7"}]
    assert respond("researcher", msgs, TOOLS["researcher"]) == respond(
        "researcher", msgs, TOOLS["researcher"]
    )
    _, calls = respond("researcher", msgs, TOOLS["researcher"])
    assert json.loads(calls[0]["function"]["arguments"]) == {"topic": "autoscaling"}
    _, calls = respond("executor", msgs, TOOLS["executor"])
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["name"] in EXECUTOR_TOOLS and args["complexity"] == 7
    content, calls = respond("analyst", msgs, None)
    assert content and not calls
    content, calls = respond("unknown", msgs, None)
    assert content and content.startswith("[fake-llm:unknown]")


def test_fault_bands_and_latency() -> None:
    p = FaultProfile(timeout_rate=0.1, error_rate_429=0.2, error_rate_500=0.3)
    assert pick_fault(p, 0.05) is Fault.TIMEOUT
    assert pick_fault(p, 0.15) is Fault.RATE_LIMIT
    assert pick_fault(p, 0.45) is Fault.SERVER_ERROR
    assert pick_fault(p, 0.7) is None
    q = FaultProfile(latency_median_ms=200, latency_sigma=0.5, latency_max_ms=1000)
    assert latency_ms(q, 0.0) == 200
    assert latency_ms(q, 1.0) == pytest.approx(200 * math.e**0.5)
    assert latency_ms(q, 10.0) == 1000


def test_fault_profile_validation() -> None:
    with pytest.raises(ValueError, match="sum"):
        FaultProfile().updated({"error_rate_429": 0.6, "error_rate_500": 0.6})
    with pytest.raises(ValueError, match="unknown"):
        FaultProfile().updated({"nope": 1})
    assert FaultProfile().updated({"error_rate_500": 0.3}).error_rate_500 == 0.3


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (None, "invalid_body"),
        ({"messages": [{"role": "user", "content": "x"}]}, "missing_model"),
        ({"model": "m", "messages": []}, "missing_messages"),
        (
            {"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 0},
            "invalid_max_tokens",
        ),
    ],
)
def test_validation_errors(body: object, code: str) -> None:
    with pytest.raises(ChatValidationError) as exc:
        validate(body)
    assert exc.value.code == code


def test_usage_is_coherent_and_respects_max_tokens() -> None:
    msgs = [{"role": "user", "content": "x" * 400}]
    out = completion(
        body={}, model="m", messages=msgs, max_tokens=5, content="y" * 400, tool_calls=[], created=0
    )
    u = out["usage"]
    assert u["completion_tokens"] == 5 and u["total_tokens"] == u["prompt_tokens"] + 5
    assert len(out["choices"][0]["message"]["content"]) == 20


class SeqRandom:
    def __init__(self, rolls: list[float]) -> None:
        self.rolls = rolls

    def random(self) -> float:
        return self.rolls.pop(0)

    def gauss(self) -> float:
        return 0.0


class Sleeper:
    def __init__(self) -> None:
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class Clock:
    def now(self) -> float:
        return 123.0


class Metrics:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def request(self, agent: str, outcome: str) -> None:
        self.outcomes.append(outcome)


async def test_use_case_injects_faults_and_latency() -> None:
    faults = FaultControl(
        FaultProfile(error_rate_500=0.3, timeout_rate=0.1, timeout_s=9, latency_median_ms=250)
    )
    sleeper, metrics = Sleeper(), Metrics()
    uc = CompleteChat(
        faults=faults, rng=SeqRandom([0.05, 0.2, 0.9]), sleeper=sleeper, clock=Clock(), metrics=metrics
    )
    body = {"model": "m", "messages": [{"role": "user", "content": "hola"}]}
    timeout = await uc(body, "a")
    err = await uc(body, "a")
    ok = await uc(body, "a")
    assert (timeout.status, err.status, ok.status) == (504, 500, 200)
    assert sleeper.slept == [9, 0.25]
    assert metrics.outcomes == ["timeout", "500", "ok"]
    assert ok.body["created"] == 123
    assert (await uc({}, "a")).status == 400
