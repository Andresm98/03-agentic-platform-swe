"""Composition root del analista."""

from __future__ import annotations

from agent_fakes import Publisher
from fastapi.testclient import TestClient

from analyst.bootstrap.main import build_app


def test_event_publishes_evaluated_then_completed() -> None:
    pub = Publisher()
    with TestClient(build_app(publisher=pub)) as c:  # type: ignore[arg-type]
        ce = {"data": {"task_id": "t", "step": 2, "role": "analysis", "goal": "g", "context": []}}
        assert c.post("/events/requested", json=ce).json() == {"status": "SUCCESS"}
        assert c.get("/dapr/subscribe").json()[0]["topic"] == "agent.analysis.requested"
    assert [t for t, _, _ in pub.sent] == ["tasks.evaluated", "agent.analysis.completed"]
