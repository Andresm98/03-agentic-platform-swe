"""Investigador: búsqueda determinista y caso de uso con fakes."""

from __future__ import annotations

from agent_fakes import Metrics, ToolLLM

from agentlib.domain.messages import AgentRequest
from researcher.application.research import Research
from researcher.domain.knowledge import Document, KnowledgeBase

KB = KnowledgeBase(
    [
        Document("a", "scale", frozenset({"keda", "scale"}), "A"),
        Document("b", "cost", frozenset({"budget"}), "B"),
    ]
)
REQ = AgentRequest(task_id="t", step=0, role="research", goal="keda budget")


def test_search_is_deterministic_and_ranked() -> None:
    r = KB.search("scale", "keda")
    assert r["hits"] == 1 and r["documents"][0]["id"] == "a" and r["documents"][0]["score"] == 7
    assert KB.search("nothing")["hits"] == 0 and len(KB) == 2


async def test_research_uses_model_chosen_topic() -> None:
    llm = ToolLLM("lookup_knowledge", {"topic": "scale"}, degraded=True)
    out = await Research(llm, Metrics(), KB)(REQ)
    assert out.result["topic"] == "scale" and out.degraded and out.llm_calls == 1
    assert llm.requests[0].tools[0].name == "lookup_knowledge" and llm.requests[0].task_id == "t"


async def test_research_without_tool_call_falls_back_to_goal() -> None:
    out = await Research(ToolLLM(None), Metrics(), KB)(REQ)
    assert out.result["hits"] == 2 and out.result["note"] == "no tool"
