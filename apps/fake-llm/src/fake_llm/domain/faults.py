"""Perfil de fallos y latencia de fake-llm (inyección de caos determinista dada una tirada)."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, fields, replace
from typing import Any


class Fault(enum.Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "429"
    SERVER_ERROR = "500"


@dataclass(frozen=True)
class FaultProfile:
    error_rate_429: float = 0.0
    error_rate_500: float = 0.0
    timeout_rate: float = 0.0
    timeout_s: float = 60.0
    latency_median_ms: float = 300.0
    latency_sigma: float = 0.5
    latency_max_ms: float = 5000.0

    _RATE_FIELDS = ("error_rate_429", "error_rate_500", "timeout_rate")

    def validate(self) -> FaultProfile:
        for name in self._RATE_FIELDS:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.error_rate_429 + self.error_rate_500 + self.timeout_rate > 1.0:
            raise ValueError("the sum of fault rates must be <= 1")
        for name in ("timeout_s", "latency_median_ms", "latency_sigma", "latency_max_ms"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        return self

    def updated(self, changes: dict[str, Any]) -> FaultProfile:
        allowed = {f.name for f in fields(self)}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown fault fields: {sorted(unknown)}")
        return replace(self, **{k: float(v) for k, v in changes.items()}).validate()

    def as_dict(self) -> dict[str, float]:
        return {f.name: float(getattr(self, f.name)) for f in fields(self)}


def pick_fault(profile: FaultProfile, roll: float) -> Fault | None:
    """`roll` ∈ [0, 1). Los tramos son contiguos: timeout, luego 429, luego 500."""
    for fault, rate in (
        (Fault.TIMEOUT, profile.timeout_rate),
        (Fault.RATE_LIMIT, profile.error_rate_429),
        (Fault.SERVER_ERROR, profile.error_rate_500),
    ):
        if roll < rate:
            return fault
        roll -= rate
    return None


def latency_ms(profile: FaultProfile, z: float) -> float:
    """Lognormal: mediana · e^(σ·z), con z ~ N(0,1), acotada a `latency_max_ms`."""
    return min(profile.latency_max_ms, profile.latency_median_ms * math.exp(profile.latency_sigma * z))
