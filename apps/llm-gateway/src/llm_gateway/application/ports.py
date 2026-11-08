"""Puertos del gateway. Solo dependen del dominio."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from llm_gateway.domain.circuit import CircuitState

Upstream = Literal["openai", "fake"]


class CasConflictError(Exception):
    """La revisión de la clave cambió entre lectura y escritura (compare-and-set)."""


class KeyValuePort(Protocol):
    """Almacén clave-valor con compare-and-set por revisión (NATS KV `llm-budget`)."""

    async def get(self, key: str) -> tuple[bytes, int] | None: ...

    async def create(self, key: str, value: bytes) -> int: ...

    async def update(self, key: str, value: bytes, last: int) -> int: ...


class UpstreamFailureError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status == 0 or self.status in {408, 409, 429, 500, 502, 503, 504}


class UpstreamPort(Protocol):
    """Proveedor compatible con OpenAI (`openai` real o `fake`). Una sola llamada, sin reintentos."""

    async def chat(
        self, upstream: Upstream, body: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]: ...


class GatewayMetricsPort(Protocol):
    def request(self, agent: str, mode: str, model: str, outcome: str) -> None: ...

    def tokens(self, agent: str, mode: str, prompt: int, completion: int) -> None: ...

    def cost(self, agent: str, model: str, usd: float) -> None: ...

    def budget_remaining(self, usd: float) -> None: ...

    def circuit(self, upstream: str, state: CircuitState) -> None: ...


@dataclass(frozen=True)
class LLMCallRecord:
    """Lo que se exporta a la telemetría LLM (LangSmith) de una llamada completada."""

    agent: str
    task_id: str
    mode: str
    model: str
    degraded: bool
    reason: str | None
    request_messages: list[dict[str, Any]]
    response_message: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    max_tokens: int
    start_s: float
    end_s: float
    cost_usd: float = 0.0
    tool_names: list[str] = field(default_factory=list)


class LLMTelemetryPort(Protocol):
    """Exportación asíncrona y no bloqueante (fail-open): nunca lanza ni espera a la red."""

    def record(self, call: LLMCallRecord) -> None: ...


class ClockPort(Protocol):
    def now(self) -> float: ...


class SleeperPort(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class RandomPort(Protocol):
    def random(self) -> float: ...
