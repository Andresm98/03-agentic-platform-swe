"""Políticas de presupuesto (ADR-0002 §6). Python puro: transiciones de estado sin E/S.

Unidades: micro-USD enteros (1 USD = 1_000_000). Con precios en USD por 1M de tokens, el coste
en micro-USD de un token es exactamente su precio: `cost = tokens_in·p_in + tokens_out·p_out`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_1m: float
    output_usd_per_1m: float

    def cost_micro(self, prompt_tokens: int, completion_tokens: int) -> int:
        return math.ceil(prompt_tokens * self.input_usd_per_1m + completion_tokens * self.output_usd_per_1m)


@dataclass(frozen=True)
class BudgetLimits:
    limit_usd: float = 3.0
    live_tasks_per_minute: int = 5
    live_tasks_total: int = 50
    task_max_llm_calls: int = 6
    task_max_tokens: int = 15000

    @property
    def limit_micro(self) -> int:
        return usd_to_micro(self.limit_usd)


@dataclass(frozen=True)
class Admission:
    ok: bool
    reason: str | None = None
    first_call: bool = False


def usd_to_micro(usd: float) -> int:
    return round(usd * 1_000_000)


def next_spent(spent_micro: int, reservation_micro: int, limit_micro: int) -> int | None:
    """Nuevo gasto tras reservar, o None si se superaría el límite."""
    total = spent_micro + reservation_micro
    return None if total > limit_micro else total


def reconciled(spent_micro: int, reserved_micro: int, actual_micro: int) -> int:
    return max(0, spent_micro - reserved_micro + actual_micro)


def incremented(count: int, cap: int) -> int | None:
    return None if count + 1 > cap else count + 1


@dataclass(frozen=True)
class TaskUsage:
    calls: int = 0
    tokens: int = 0

    @classmethod
    def decode(cls, raw: bytes | None) -> TaskUsage:
        if not raw:
            return cls()
        data = json.loads(raw)
        return cls(calls=int(data.get("calls", 0)), tokens=int(data.get("tokens", 0)))

    def encode(self) -> bytes:
        return json.dumps({"calls": self.calls, "tokens": self.tokens}).encode()


def admit_task_call(
    usage: TaskUsage, limits: BudgetLimits, est_tokens: int
) -> tuple[TaskUsage | None, Admission]:
    """Cuenta una llamada live de una tarea contra sus límites de pasos y tokens."""
    if usage.calls + 1 > limits.task_max_llm_calls:
        return None, Admission(False, "task_step_limit")
    if usage.tokens + est_tokens > limits.task_max_tokens:
        return None, Admission(False, "task_token_limit")
    return TaskUsage(usage.calls + 1, usage.tokens + est_tokens), Admission(True, first_call=usage.calls == 0)
