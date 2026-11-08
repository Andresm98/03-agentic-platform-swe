"""Circuit breaker por upstream: cerrado → abierto → semiabierto → cerrado. Python puro.

Se abre con `threshold` fallos (429/5xx/timeout) dentro de `window_s`; abierto durante `open_s`;
después deja pasar una sola sonda (semiabierto): si va bien se cierra y si falla vuelve a abrir.
El estado es por réplica: con 2 réplicas hay 2 circuitos, aceptable porque solo corta llamadas.
"""

from __future__ import annotations

import enum
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


class CircuitState(enum.IntEnum):
    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


@dataclass(frozen=True)
class CircuitConfig:
    threshold: int = 5
    window_s: float = 30.0
    open_s: float = 30.0


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        config: CircuitConfig,
        clock: Callable[[], float],
        on_change: Callable[[str, CircuitState], None] = lambda _n, _s: None,
    ) -> None:
        self.name = name
        self._cfg = config
        self._clock = clock
        self._on_change = on_change
        self._failures: deque[float] = deque()
        self._state = CircuitState.CLOSED
        self._opened_at = 0.0
        self._probe_in_flight = False
        on_change(name, self._state)

    @property
    def state(self) -> CircuitState:
        self._maybe_half_open()
        return self._state

    def _set(self, state: CircuitState) -> None:
        if state != self._state:
            self._state = state
            self._on_change(self.name, state)

    def _maybe_half_open(self) -> None:
        if self._state == CircuitState.OPEN and self._clock() - self._opened_at >= self._cfg.open_s:
            self._probe_in_flight = False
            self._set(CircuitState.HALF_OPEN)

    def allow(self) -> bool:
        self._maybe_half_open()
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN and not self._probe_in_flight:
            self._probe_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        self._failures.clear()
        self._probe_in_flight = False
        self._set(CircuitState.CLOSED)

    def record_failure(self) -> None:
        now = self._clock()
        if self._state == CircuitState.HALF_OPEN:
            self._open(now)
            return
        self._failures.append(now)
        while self._failures and now - self._failures[0] > self._cfg.window_s:
            self._failures.popleft()
        if len(self._failures) >= self._cfg.threshold:
            self._open(now)

    def _open(self, now: float) -> None:
        self._opened_at = now
        self._failures.clear()
        self._probe_in_flight = False
        self._set(CircuitState.OPEN)
