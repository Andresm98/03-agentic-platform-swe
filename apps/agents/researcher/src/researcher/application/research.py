"""Caso de uso Research: el modelo elige el tema y la búsqueda se hace en la base local."""

from __future__ import annotations

from typing import Protocol

from agentlib.application.agent_loop import LoopConfig, run_agent_loop
from agentlib.application.handle_request import WorkOutput
from agentlib.application.ports import AgentMetricsPort, LLMPort
from agentlib.domain.chat import ChatRequest, ToolSpec
from agentlib.domain.messages import AgentRequest
from researcher.domain.knowledge import KnowledgeBase

TOOLS = (
    ToolSpec(
        "lookup_knowledge",
        "Search the local, versioned knowledge base for a topic and return matching documents.",
        {"topic": {"type": "string", "maxLength": 80}},
        ("topic",),
    ),
)
SYSTEM = "You are the researcher agent. Pick ONE topic to look up with lookup_knowledge."


class KnowledgeRepositoryPort(Protocol):
    def load(self) -> KnowledgeBase: ...


class Research:
    def __init__(
        self, llm: LLMPort, metrics: AgentMetricsPort, kb: KnowledgeBase, max_llm_calls: int = 1
    ) -> None:
        self._llm, self._metrics, self._kb, self._max = llm, metrics, kb, max_llm_calls

    async def __call__(self, req: AgentRequest) -> WorkOutput:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{req.goal}\ninstructions: {req.args.get('instructions', '')}"},
        ]

        def lookup(topic: str) -> dict[str, object]:
            return self._kb.search(str(topic)[:80], req.goal)

        loop = await run_agent_loop(
            self._llm,
            self._metrics,
            ChatRequest(messages, req.task_id, req.mode, TOOLS, req.traceparent),
            {"lookup_knowledge": lookup},
            LoopConfig(max_steps=self._max),
        )
        result = (
            dict(loop.tool_results[-1]["result"])
            if loop.tool_results
            else self._kb.search(req.goal[:80], req.goal)
        )
        result["note"] = loop.final
        return WorkOutput(result, loop.degraded, loop.steps)
