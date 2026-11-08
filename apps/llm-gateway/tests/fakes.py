"""Dobles en memoria para los tests del gateway (sin red ni NATS)."""

from __future__ import annotations

import asyncio
from typing import Any

from llm_gateway.adapters.outbound.kv import InMemoryKeyValue
from llm_gateway.application.ports import LLMCallRecord, Upstream, UpstreamFailureError
from llm_gateway.domain.circuit import CircuitState


def completion(
    content: str = "ok", prompt: int = 100, completion_tokens: int = 50, model: str = "gpt-4o-mini"
) -> dict[str, Any]:
    return {
        "id": "chatcmpl-x",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt + completion_tokens,
        },
    }


class FakeUpstream:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.fail: dict[str, list[int]] = {"openai": [], "fake": []}

    async def chat(self, upstream: Upstream, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        self.calls.append((upstream, body, headers))
        if self.fail[upstream]:
            raise UpstreamFailureError(self.fail[upstream].pop(0), "injected")
        return completion(content=f"from-{upstream}", model=body["model"])

    def count(self, upstream: str) -> int:
        return sum(1 for u, _, _ in self.calls if u == upstream)


class RecordingMetrics:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str, str]] = []
        self.token_calls: list[tuple[str, str, int, int]] = []
        self.costs: list[float] = []
        self.remaining: float | None = None
        self.circuits: dict[str, CircuitState] = {}

    def request(self, agent: str, mode: str, model: str, outcome: str) -> None:
        self.requests.append((agent, mode, model, outcome))

    def tokens(self, agent: str, mode: str, prompt: int, completion: int) -> None:
        self.token_calls.append((agent, mode, prompt, completion))

    def cost(self, agent: str, model: str, usd: float) -> None:
        self.costs.append(usd)

    def budget_remaining(self, usd: float) -> None:
        self.remaining = usd

    def circuit(self, upstream: str, state: CircuitState) -> None:
        self.circuits[upstream] = state

    def live_tokens(self) -> int:
        return sum(p + c for _, mode, p, c in self.token_calls if mode == "live")


class RecordingTelemetry:
    def __init__(self, raise_on_record: bool = False) -> None:
        self.records: list[LLMCallRecord] = []
        self.raise_on_record = raise_on_record

    def record(self, call: LLMCallRecord) -> None:
        if self.raise_on_record:
            raise RuntimeError("telemetry down")
        self.records.append(call)


class ManualClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t


class NoSleep:
    def __init__(self) -> None:
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class FixedRandom:
    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


class YieldingKV(InMemoryKeyValue):
    """Cede el control entre lectura y escritura para provocar conflictos CAS reales."""

    async def get(self, key: str) -> tuple[bytes, int] | None:
        value = await super().get(key)
        await asyncio.sleep(0)
        return value
