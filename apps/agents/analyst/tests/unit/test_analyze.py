"""Análisis: puntuación determinista y publicación de tasks.evaluated."""

from __future__ import annotations

from agent_fakes import Publisher

from agentlib.domain.messages import AgentRequest
from analyst.application.analyze import Analyze
from analyst.domain.scoring import score

GOOD = [
    {"role": "research", "status": "ok", "result": {"hits": 3}},
    {"role": "execution", "status": "ok", "result": {"primes": 5}},
]


def test_score_full_marks_and_breakdown() -> None:
    ev = score(GOOD, "goal")
    assert ev.score == 100 and ev.verdict == "pass" and ev.evidence == 2 and not ev.degraded_inputs


def test_score_penalises_errors_and_missing_execution() -> None:
    bad = [{"role": "execution", "status": "timeout", "result": {}, "degraded": True}]
    ev = score(bad, "goal")
    assert ev.breakdown == {"research": 0, "execution": 0, "reliability": 10, "goal": 10}
    assert ev.verdict == "fail" and ev.degraded_inputs
    assert (
        score([{"role": "execution", "status": "ok", "result": {"error": "x"}}], " ").breakdown["goal"] == 0
    )


def test_score_is_deterministic() -> None:
    assert score(GOOD, "g") == score(GOOD, "g")


async def test_analyze_publishes_tasks_evaluated() -> None:
    pub = Publisher()
    req = AgentRequest(task_id="t", step=2, role="analysis", goal="g", context=GOOD, mode="live")
    out = await Analyze(pub)(req)
    topic, data, msg_id = pub.sent[0]
    assert topic == "tasks.evaluated" and data["task_id"] == "t" and data["score"] == 100
    assert data["mode"] == "live" and msg_id == "t:2:tasks.evaluated"
    assert out.result["verdict"] == "pass" and out.llm_calls == 0
