"""Composition root del investigador con la base de conocimiento real empaquetada."""

from __future__ import annotations

from agent_fakes import Publisher, ToolLLM
from fastapi.testclient import TestClient

from researcher.adapters.outbound.json_knowledge import PackagedKnowledge
from researcher.bootstrap.main import build_app


def test_packaged_knowledge_loads() -> None:
    kb = PackagedKnowledge().load()
    assert len(kb) == 8 and kb.search("autoscaling", "keda")["documents"][0]["id"] == "kb-001"


def test_event_flow_publishes_completed() -> None:
    pub = Publisher()
    app = build_app(llm=ToolLLM("lookup_knowledge", {"topic": "cost"}), publisher=pub)  # type: ignore[arg-type]
    with TestClient(app) as c:
        ce = {"data": {"task_id": "t", "step": 1, "role": "research", "goal": "coste"}}
        assert c.post("/events/requested", json=ce).json() == {"status": "SUCCESS"}
        assert c.get("/dapr/subscribe").json()[0]["topic"] == "agent.research.requested"
    topic, data, msg_id = pub.sent[0]
    assert topic == "agent.research.completed" and data["result"]["hits"] >= 1
    assert msg_id == "t:1:agent.research.completed"
