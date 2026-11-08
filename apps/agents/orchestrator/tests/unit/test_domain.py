"""Dominio del orquestador: admisión, especificación, backpressure y TaskRun."""

from __future__ import annotations

import pytest

from orchestrator.domain.plan import Decision, TaskRun, build_messages, decision_from_calls
from orchestrator.domain.task import AdmissionPolicy, InvalidTaskError, ShedPolicy, TaskSpec


def test_admission_only_valid_token_is_live() -> None:
    policy = AdmissionPolicy("s3cret-demo-token")
    assert policy.decide(None).mode == "simulated" and policy.decide(None).token == "absent"
    assert policy.decide("wrong").mode == "simulated" and policy.decide("wrong").token == "invalid"
    assert policy.decide("s3cret-demo-token").mode == "live"
    assert policy.decide("s3cret-demo-token ").mode == "simulated"
    assert policy.decide("ñ" * 2000).mode == "simulated"  # tokens enormes o no ASCII no rompen nada


def test_admission_without_configured_token_never_live() -> None:
    policy = AdmissionPolicy("")
    assert policy.decide("").mode == "simulated"
    assert policy.decide("\x00" * 32).mode == "simulated"


@pytest.mark.parametrize(
    ("goal", "cx"), [("", 3), ("   ", 3), ("x" * 2001, 3), ("ok", 0), ("ok", 11), ("ok", True)]
)
def test_task_spec_validation(goal: str, cx: int) -> None:
    with pytest.raises(InvalidTaskError):
        TaskSpec(goal, cx)


def test_shed_policy() -> None:
    p = ShedPolicy(threshold=10)
    assert not p.should_shed(None) and not p.should_shed(9) and p.should_shed(10)


def test_decision_parsing() -> None:
    d = decision_from_calls([("c1", "dispatch_research", {"instructions": "x"})], None, True, 0)
    assert d.role == "research" and not d.finishes and d.degraded
    d = decision_from_calls([("c1", "rm_rf", {})], None, False, 2)
    assert d.finishes and "unknown tool" in (d.note or "") and d.call_id == "call_auto_2"
    d = decision_from_calls([], "I am done", False, 1)
    assert d.finishes and d.args["summary"] == "I am done"
    assert Decision.from_dict(d.to_dict()) == d


INP = {"task_id": "t", "goal": "g", "complexity": 2, "mode": "simulated", "created_at": 10.0, "max_steps": 6}


def test_task_run_happy_path_and_outcome() -> None:
    run = TaskRun.start(INP)
    run.apply_decision(Decision("dispatch_research", "c0"))
    dispatch = run.dispatch_input()
    assert dispatch["role"] == "research" and dispatch["step"] == 0
    run.apply_result({"status": "ok", "result": {"hits": 2}, "agent": "researcher", "degraded": True})
    run.apply_decision(Decision("dispatch_analysis", "c1"))
    run.apply_result({"status": "ok", "result": {"score": 80}})
    run.apply_decision(Decision("finish", "c2", {"summary": "done"}))
    out = run.outcome()
    assert out["status"] == "completed" and out["finish_reason"] == "finish" and out["degraded"]
    assert out["evaluation"] == {"score": 80} and len(out["steps"]) == 2


def test_task_run_step_limit_and_timeout() -> None:
    run = TaskRun.start({**INP, "max_steps": 2})
    run.apply_decision(Decision("dispatch_execution", "c0"))
    run.apply_result(None)
    assert run.steps[0].status == "timeout" and not run.done
    run.apply_decision(Decision("dispatch_execution", "c1"))
    run.apply_result({"status": "ok"})
    assert run.done and run.finish_reason == "step_limit"
    run2 = TaskRun.start(INP)
    run2.fail("activity_failed")
    assert run2.outcome()["status"] == "failed"


def test_build_messages_pairs_tool_calls() -> None:
    history = [
        {"call_id": "c0", "tool": "dispatch_research", "status": "ok", "agent": "r", "result": {"x": 1}}
    ]
    msgs = build_messages("goal", 4, history)
    assert msgs[1]["content"].endswith("complexity=4")
    assert msgs[2]["tool_calls"][0]["id"] == "c0" and msgs[3]["tool_call_id"] == "c0"
