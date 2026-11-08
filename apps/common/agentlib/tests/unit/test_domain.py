"""Dominio común: mensajes, chat/recorte de contexto e ids."""

from __future__ import annotations

import uuid

import pytest

from agentlib.domain.chat import ToolSpec, estimate_tokens, trim_messages
from agentlib.domain.errors import InvalidMessageError
from agentlib.domain.ids import Uuid7Factory, is_uuid
from agentlib.domain.messages import (
    AgentRequest,
    AgentResult,
    completed_topic,
    message_id,
    requested_topic,
    result_event_name,
)

REQ = {"task_id": "t", "step": 1, "role": "research", "goal": "g", "mode": "live", "complexity": 4}


def test_agent_request_roundtrip_and_defaults() -> None:
    req = AgentRequest.from_dict({**REQ, "args": {"a": 1}, "context": [{"x": 1}, "junk"]})
    assert req.mode == "live" and req.complexity == 4 and req.context == [{"x": 1}]
    assert AgentRequest.from_dict(req.to_dict()) == req
    assert (
        AgentRequest.from_dict({k: v for k, v in REQ.items() if k not in ("mode", "complexity")}).mode
        == "simulated"
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {**REQ, "step": -1},
        {**REQ, "step": True},
        {**REQ, "role": "hack"},
        {**REQ, "mode": "turbo"},
        {**REQ, "complexity": 11},
        {**REQ, "goal": "x" * 4001},
        {**REQ, "task_id": 5},
        {**REQ, "args": []},
    ],
)
def test_agent_request_rejects_invalid(bad: object) -> None:
    with pytest.raises(InvalidMessageError):
        AgentRequest.from_dict(bad)


def test_agent_result_roundtrip_and_validation() -> None:
    res = AgentResult(task_id="t", step=2, role="execution", agent="executor", result={"v": 1}, degraded=True)
    assert AgentResult.from_dict(res.to_dict()) == res
    assert AgentResult.from_dict({**res.to_dict(), "result": 5}).result == {"value": 5}
    with pytest.raises(InvalidMessageError):
        AgentResult.from_dict({**res.to_dict(), "status": "weird"})
    with pytest.raises(InvalidMessageError):
        AgentResult.from_dict([])


def test_topics_and_ids() -> None:
    assert requested_topic("analysis") == "agent.analysis.requested"
    assert completed_topic("execution") == "agent.execution.completed"
    assert result_event_name(3) == "agent_result_3"
    assert message_id("t", 2, "x.y") == "t:2:x.y"


def test_trim_keeps_head_and_drops_whole_turns() -> None:
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "goal"}]
    for i in range(30):
        msgs += [
            {"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}"}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "r" * 200},
        ]
    out = trim_messages(msgs, 400)
    assert out[:2] == msgs[:2] and estimate_tokens(out) <= 400
    assert out[2]["role"] == "assistant"  # nunca empieza por un tool huérfano
    assert trim_messages(msgs[:2], 400) == msgs[:2]
    huge = [{"role": "system", "content": "s" * 5000}, {"role": "user", "content": "u" * 5000}]
    assert estimate_tokens(trim_messages(huge, 200)) <= 200


def test_tool_spec_openai_shape() -> None:
    spec = ToolSpec("f", "d", {"a": {"type": "string"}}, ("a",)).to_openai()
    assert spec["function"]["parameters"]["required"] == ["a"]
    assert spec["function"]["parameters"]["additionalProperties"] is False


def test_uuid7_is_valid_monotonic_and_versioned() -> None:
    t = [1_700_000_000_000_000_000]
    f = Uuid7Factory(clock_ns=lambda: t[0])
    ids = [f.new() for _ in range(5000)]  # mismo ms: el contador desborda y avanza el reloj lógico
    assert ids == sorted(ids) and len(set(ids)) == 5000
    u = uuid.UUID(ids[0])
    assert u.version == 7 and u.variant == uuid.RFC_4122 and is_uuid(ids[0])
    t[0] += 10**9
    assert f.new() > ids[-1]
    assert not is_uuid("not-a-uuid")
