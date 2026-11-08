"""Adaptador Prometheus de `GatewayMetricsPort` y adaptadores de sistema (reloj, sleep, azar)."""

from __future__ import annotations

import asyncio
import random
import time

from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics
from llm_gateway.domain.circuit import CircuitState


class PrometheusGatewayMetrics:
    def __init__(self, metrics: FleetMetrics) -> None:
        self._m = metrics

    def request(self, agent: str, mode: str, model: str, outcome: str) -> None:
        self._m.llm_requests.labels(agent, mode, model[:40], outcome).inc()

    def tokens(self, agent: str, mode: str, prompt: int, completion: int) -> None:
        self._m.llm_tokens.labels(agent, mode, "input").inc(prompt)
        self._m.llm_tokens.labels(agent, mode, "output").inc(completion)

    def cost(self, agent: str, model: str, usd: float) -> None:
        self._m.llm_cost.labels(agent, model).inc(usd)

    def budget_remaining(self, usd: float) -> None:
        self._m.llm_budget_remaining.set(usd)

    def circuit(self, upstream: str, state: CircuitState) -> None:
        self._m.llm_circuit_state.labels(upstream).set(int(state))


class MonotonicClock:
    def now(self) -> float:
        return time.time()


class AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class SystemRandom:
    def __init__(self) -> None:
        self._rng = random.Random()  # noqa: S311 - jitter y muestreo, no criptografía

    def random(self) -> float:
        return self._rng.random()
