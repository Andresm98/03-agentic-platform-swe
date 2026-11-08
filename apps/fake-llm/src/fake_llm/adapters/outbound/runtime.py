"""Adaptadores de salida de fake-llm: aleatoriedad sembrada, sleep asíncrono y métricas."""

from __future__ import annotations

import asyncio
import random
import time

from prometheus_client import CollectorRegistry, Counter


class SeededRandom:
    """Implementa `RandomPort`. Semilla fija → misma secuencia de fallos y latencias."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)  # noqa: S311 - simulación, no criptografía

    def random(self) -> float:
        return self._rng.random()

    def gauss(self) -> float:
        return self._rng.gauss(0.0, 1.0)


class AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class WallClock:
    def now(self) -> float:
        return time.time()


class PrometheusFakeMetrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self._requests = Counter(
            "fake_llm_requests_total", "Peticiones a fake-llm", ["agent", "outcome"], registry=registry
        )

    def request(self, agent: str, outcome: str) -> None:
        self._requests.labels(agent[:40], outcome).inc()
