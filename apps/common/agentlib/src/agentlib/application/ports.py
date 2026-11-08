"""Puertos comunes (salida) que implementan los adaptadores. Solo dependen del dominio."""

from __future__ import annotations

from typing import Any, Protocol

from agentlib.domain.chat import ChatRequest, ChatResult


class LLMPort(Protocol):
    """Modelo de lenguaje accesible vía `llm-gateway` (API compatible con OpenAI)."""

    @property
    def agent(self) -> str: ...

    async def complete(self, request: ChatRequest) -> ChatResult: ...


class EventPublisherPort(Protocol):
    """Publicación en el bus (Dapr pub/sub `pubsub`). Lanza `PublishRejectedError` si falla."""

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None: ...


class ClockPort(Protocol):
    def now(self) -> float: ...


class IdGeneratorPort(Protocol):
    def new(self) -> str: ...


class AgentMetricsPort(Protocol):
    """Telemetría de negocio de un agente (implementada con Prometheus)."""

    def message_processed(self, agent: str, status: str, seconds: float | None = None) -> None: ...

    def agent_step(self, agent: str) -> None: ...


class TracerPort(Protocol):
    """Spans propios (decisión del modelo, herramienta). El contexto llega como `traceparent`."""

    def span(self, name: str, traceparent: str | None, attributes: dict[str, Any]) -> Any: ...
