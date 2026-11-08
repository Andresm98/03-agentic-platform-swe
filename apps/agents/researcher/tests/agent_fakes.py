"""Dobles en memoria compartidos por los tests de este agente."""

from __future__ import annotations

from typing import Any

from agentlib.domain.chat import ChatRequest, ChatResult, ToolCall


class ToolLLM:
    def __init__(self, name: str | None, args: dict[str, Any] | None = None, degraded: bool = False) -> None:
        self.name, self.args, self.degraded = name, args or {}, degraded
        self.requests: list[ChatRequest] = []

    @property
    def agent(self) -> str:
        return "agent"

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.requests.append(request)
        if self.name is None:
            return ChatResult("no tool", degraded=self.degraded)
        call = ToolCall("c1", self.name, self.args)
        message = {"role": "assistant", "tool_calls": [{"id": "c1"}]}
        return ChatResult(None, (call,), degraded=self.degraded, message=message)


class Metrics:
    def message_processed(self, agent: str, status: str, seconds: float | None = None) -> None:
        return None

    def agent_step(self, agent: str) -> None:
        return None


class Publisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any], str]] = []

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None:
        self.sent.append((topic, data, msg_id))

    async def healthy(self) -> bool:
        return True
