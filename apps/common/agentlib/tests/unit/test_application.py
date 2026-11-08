"""Aplicación común: bucle de agente y HandleAgentRequest con fakes en memoria."""

from __future__ import annotations

from typing import Any

from agentlib.application.agent_loop import LoopConfig, run_agent_loop
from agentlib.application.handle_request import HandleAgentRequest, Outcome, WorkOutput
from agentlib.domain.chat import ChatRequest, ChatResult, ToolCall
from agentlib.domain.errors import PublishRejectedError, TransientDependencyError
from agentlib.domain.messages import AgentRequest


class ScriptedLLM:
    def __init__(self, results: list[ChatResult]) -> None:
        self.results = results
        self.requests: list[ChatRequest] = []

    @property
    def agent(self) -> str:
        return "tester"

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.requests.append(request)
        return self.results.pop(0)


class Metrics:
    def __init__(self) -> None:
        self.processed: list[str] = []
        self.steps = 0

    def message_processed(self, agent: str, status: str, seconds: float | None = None) -> None:
        self.processed.append(status)

    def agent_step(self, agent: str) -> None:
        self.steps += 1


class Publisher:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, dict[str, Any], str, str | None]] = []
        self.fail = fail

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None:
        if self.fail:
            raise PublishRejectedError("full")
        self.sent.append((topic, data, msg_id, traceparent))


def _call(name: str, args: dict[str, Any], cid: str = "c1") -> ChatResult:
    return ChatResult(
        None,
        (ToolCall(cid, name, args),),
        message={"role": "assistant", "tool_calls": [{"id": cid}]},
        degraded=True,
    )


REQ = ChatRequest([{"role": "user", "content": "g"}], "t", "simulated")


async def test_loop_runs_tool_without_summary_call() -> None:
    llm, m = ScriptedLLM([_call("add", {"a": 1, "b": 2})]), Metrics()
    out = await run_agent_loop(llm, m, REQ, {"add": lambda a, b: {"sum": a + b}}, LoopConfig(max_steps=3))
    assert out.tool_results[0]["result"] == {"sum": 3} and out.steps == 1 and out.degraded and m.steps == 1


async def test_loop_summarize_until_final_and_handles_bad_tools() -> None:
    async def slow(x: int) -> int:
        return x * 2

    llm = ScriptedLLM(
        [
            _call("nope", {}),
            _call("slow", {"x": 2}, "c2"),
            _call("slow", {"bad": 1}, "c3"),
            ChatResult("done"),
        ]
    )
    out = await run_agent_loop(llm, Metrics(), REQ, {"slow": slow}, LoopConfig(max_steps=5, summarize=True))
    assert out.final == "done" and out.steps == 4
    assert "unknown tool" in out.tool_results[0]["result"]["error"]
    assert (
        out.tool_results[1]["result"] == 4 and "invalid arguments" in out.tool_results[2]["result"]["error"]
    )
    assert llm.requests[-1].messages[-1]["role"] == "tool"


async def test_loop_stops_at_step_limit() -> None:
    llm = ScriptedLLM([_call("t", {}), _call("t", {}, "c2")])
    out = await run_agent_loop(llm, Metrics(), REQ, {"t": lambda: 1}, LoopConfig(max_steps=2, summarize=True))
    assert out.stopped_by_limit and out.steps == 2


def _handler(work: Any, publisher: Publisher, metrics: Metrics) -> HandleAgentRequest:
    return HandleAgentRequest(agent="researcher", pod="p1", work=work, publisher=publisher, metrics=metrics)


PAYLOAD = {"task_id": "t1", "step": 0, "role": "research", "goal": "g"}


async def test_handle_success_publishes_completed_with_deterministic_id() -> None:
    async def work(req: AgentRequest) -> WorkOutput:
        assert req.traceparent == "tp"
        return WorkOutput({"hits": 2}, degraded=True, llm_calls=1)

    pub, m = Publisher(), Metrics()
    assert await _handler(work, pub, m)(PAYLOAD, "tp") is Outcome.SUCCESS
    topic, data, msg_id, tp = pub.sent[0]
    assert topic == "agent.research.completed" and msg_id == "t1:0:agent.research.completed" and tp == "tp"
    assert data["result"] == {"hits": 2} and data["degraded"] and data["pod"] == "p1"
    assert m.processed == ["ok"]


async def test_handle_outcomes() -> None:
    async def transient(req: AgentRequest) -> WorkOutput:
        raise TransientDependencyError("gw down")

    async def boom(req: AgentRequest) -> WorkOutput:
        raise RuntimeError("bad input")

    async def ok(req: AgentRequest) -> WorkOutput:
        return WorkOutput({})

    m = Metrics()
    assert await _handler(ok, Publisher(), m)({"nope": 1}, None) is Outcome.DROP
    assert await _handler(transient, Publisher(), m)(PAYLOAD, None) is Outcome.RETRY
    pub = Publisher()
    assert await _handler(boom, pub, m)(PAYLOAD, None) is Outcome.SUCCESS
    assert pub.sent[0][1]["status"] == "error" and "bad input" in pub.sent[0][1]["result"]["error"]
    assert await _handler(ok, Publisher(fail=True), m)(PAYLOAD, None) is Outcome.RETRY
    assert m.processed == ["invalid", "retry", "error", "retry"]
