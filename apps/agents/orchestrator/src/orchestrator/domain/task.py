"""Entidad Task, especificación validada y política de admisión (X-Demo-Token). Python puro."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Literal

Mode = Literal["live", "simulated"]
TokenState = Literal["absent", "valid", "invalid"]
MAX_GOAL_CHARS = 2000


class InvalidTaskError(ValueError):
    """La petición no cumple la especificación de una tarea (→ 422)."""


@dataclass(frozen=True)
class TaskSpec:
    goal: str
    complexity: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise InvalidTaskError("goal must be a non-empty string")
        if len(self.goal) > MAX_GOAL_CHARS:
            raise InvalidTaskError(f"goal must be at most {MAX_GOAL_CHARS} characters")
        if (
            not isinstance(self.complexity, int)
            or isinstance(self.complexity, bool)
            or not 1 <= self.complexity <= 10
        ):
            raise InvalidTaskError("complexity must be an integer between 1 and 10")


@dataclass(frozen=True)
class AdmissionDecision:
    mode: Mode
    token: TokenState


class AdmissionPolicy:
    """Barrera 1 de ADR-0002 §6: solo un `X-Demo-Token` válido obtiene `live`.

    - Comparación en tiempo constante (`hmac.compare_digest`) sobre bytes.
    - Sin token configurado, nadie obtiene `live` (fallo seguro).
    - Un token inválido no da error: la tarea se acepta en `simulated` y no se revela nada.
    """

    def __init__(self, demo_token: str) -> None:
        self._token = demo_token.encode() if demo_token else b""

    def decide(self, presented: str | None) -> AdmissionDecision:
        if not presented:
            return AdmissionDecision("simulated", "absent")
        candidate = presented.encode("utf-8", errors="replace")[:512]
        # Se compara siempre (aunque no haya token configurado) para no filtrar por tiempo.
        valid = hmac.compare_digest(candidate, self._token or b"\x00" * 32) and bool(self._token)
        return AdmissionDecision("live", "valid") if valid else AdmissionDecision("simulated", "invalid")


@dataclass(frozen=True)
class ShedPolicy:
    """Backpressure: con la cola por encima del umbral se rechaza con 429 + Retry-After."""

    threshold: int = 5000
    retry_after_s: int = 5

    def should_shed(self, queue_depth: int | None) -> bool:
        return queue_depth is not None and queue_depth >= self.threshold
