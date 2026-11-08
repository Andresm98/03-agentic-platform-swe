"""Casos de uso de fake-llm: completar un chat (con caos inyectado) y ajustar los fallos."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from fake_llm.domain.completion import ChatValidationError, completion, error_body, validate
from fake_llm.domain.faults import Fault, FaultProfile, latency_ms, pick_fault
from fake_llm.domain.scripts import respond


class RandomPort(Protocol):
    def random(self) -> float: ...

    def gauss(self) -> float: ...


class SleeperPort(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class ClockPort(Protocol):
    def now(self) -> float: ...


class FakeMetricsPort(Protocol):
    def request(self, agent: str, outcome: str) -> None: ...


@dataclass(frozen=True)
class ChatOutcome:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


_FAULT_RESPONSES: dict[Fault, ChatOutcome] = {
    Fault.TIMEOUT: ChatOutcome(504, error_body("Upstream timed out (injected)", "server_error", "timeout")),
    Fault.RATE_LIMIT: ChatOutcome(
        429,
        error_body("Rate limit reached (injected)", "rate_limit_error", "rate_limit_exceeded"),
        {"Retry-After": "1"},
    ),
    Fault.SERVER_ERROR: ChatOutcome(
        500, error_body("Internal server error (injected)", "server_error", "server_error")
    ),
}


class FaultControl:
    """Estado mutable de la inyección de fallos (instancia única creada en el composition root)."""

    def __init__(self, profile: FaultProfile) -> None:
        self.profile = profile.validate()

    def update(self, changes: dict[str, Any]) -> FaultProfile:
        self.profile = self.profile.updated(changes)
        return self.profile


class CompleteChat:
    def __init__(
        self,
        *,
        faults: FaultControl,
        rng: RandomPort,
        sleeper: SleeperPort,
        clock: ClockPort,
        metrics: FakeMetricsPort,
    ) -> None:
        self._faults = faults
        self._rng = rng
        self._sleeper = sleeper
        self._clock = clock
        self._metrics = metrics

    async def __call__(self, body: Any, agent: str) -> ChatOutcome:
        try:
            model, messages, max_tokens = validate(body)
        except ChatValidationError as exc:
            self._metrics.request(agent, "invalid")
            return ChatOutcome(400, error_body(str(exc), "invalid_request_error", exc.code))
        profile = self._faults.profile
        fault = pick_fault(profile, self._rng.random())
        if fault is not None:
            self._metrics.request(agent, fault.value)
            if fault is Fault.TIMEOUT:
                await self._sleeper.sleep(profile.timeout_s)
            return _FAULT_RESPONSES[fault]
        await self._sleeper.sleep(latency_ms(profile, self._rng.gauss()) / 1000.0)
        content, tool_calls = respond(agent, messages, body.get("tools"))
        self._metrics.request(agent, "ok")
        return ChatOutcome(
            200,
            completion(
                body=body,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                content=content,
                tool_calls=tool_calls,
                created=int(self._clock.now()),
            ),
        )
