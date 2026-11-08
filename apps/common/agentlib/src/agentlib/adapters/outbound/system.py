"""Adaptadores de reloj e ids (`ClockPort`, `IdGeneratorPort`)."""

from __future__ import annotations

import time

from agentlib.domain.ids import Uuid7Factory


class SystemClock:
    def now(self) -> float:
        return time.time()


class Uuid7Generator:
    def __init__(self) -> None:
        self._factory = Uuid7Factory()

    def new(self) -> str:
        return self._factory.new()
