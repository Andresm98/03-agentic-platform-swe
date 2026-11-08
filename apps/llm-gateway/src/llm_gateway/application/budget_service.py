"""Caso de uso: reservar y conciliar presupuesto y contar llamadas/tareas live en el KV compartido.

Todas las escrituras son compare-and-set (`update(last=rev)`), así que las 2 réplicas del gateway
comparten un único tope sin carreras. Claves: `spent_micro_usd`, `live_tasks_total`,
`live_tasks_minute.<epoch_min>`, `task.<task_id>`.
"""

from __future__ import annotations

from collections.abc import Callable

from llm_gateway.application.ports import CasConflictError, KeyValuePort
from llm_gateway.domain.budget import (
    Admission,
    BudgetLimits,
    TaskUsage,
    admit_task_call,
    incremented,
    next_spent,
    reconciled,
)

SPENT_KEY = "spent_micro_usd"
TOTAL_KEY = "live_tasks_total"


class ContentionError(Exception):
    """Demasiados conflictos de CAS seguidos: se trata como fallo transitorio."""


async def cas_update(
    kv: KeyValuePort, key: str, fn: Callable[[bytes | None], bytes | None], attempts: int = 16
) -> bytes | None:
    """Aplica `fn` de forma atómica. Si `fn` devuelve None, aborta sin escribir."""
    for _ in range(attempts):
        cur = await kv.get(key)
        new = fn(cur[0] if cur else None)
        if new is None:
            return None
        try:
            if cur is None:
                await kv.create(key, new)
            else:
                await kv.update(key, new, last=cur[1])
            return new
        except CasConflictError:
            continue
    raise ContentionError(key)


def _int(raw: bytes | None) -> int:
    return int(raw) if raw else 0


class BudgetService:
    def __init__(self, kv: KeyValuePort, limits: BudgetLimits) -> None:
        self._kv = kv
        self.limits = limits

    async def remaining_usd(self) -> float:
        cur = await self._kv.get(SPENT_KEY)
        spent = _int(cur[0]) if cur else 0
        return max(0, self.limits.limit_micro - spent) / 1_000_000

    async def reserve(self, micro: int) -> Admission:
        def fn(old: bytes | None) -> bytes | None:
            new = next_spent(_int(old), micro, self.limits.limit_micro)
            return None if new is None else str(new).encode()

        ok = await cas_update(self._kv, SPENT_KEY, fn) is not None
        return Admission(True) if ok else Admission(False, "budget_exhausted")

    async def reconcile(self, reserved_micro: int, actual_micro: int) -> None:
        if reserved_micro == actual_micro:
            return
        await cas_update(
            self._kv, SPENT_KEY, lambda old: str(reconciled(_int(old), reserved_micro, actual_micro)).encode()
        )

    async def admit_task_call(self, task_id: str, epoch_minute: int, est_tokens: int) -> Admission:
        verdict = Admission(False, "contention")

        def fn(old: bytes | None) -> bytes | None:
            nonlocal verdict
            new, verdict = admit_task_call(TaskUsage.decode(old), self.limits, est_tokens)
            return None if new is None else new.encode()

        await cas_update(self._kv, f"task.{task_id}", fn)
        if not verdict.ok or not verdict.first_call:
            return verdict
        if not await self._incr_capped(
            f"live_tasks_minute.{epoch_minute}", self.limits.live_tasks_per_minute
        ):
            return Admission(False, "live_rate_limit")
        if not await self._incr_capped(TOTAL_KEY, self.limits.live_tasks_total):
            return Admission(False, "live_total_limit")
        return verdict

    async def _incr_capped(self, key: str, cap: int) -> bool:
        def fn(old: bytes | None) -> bytes | None:
            new = incremented(_int(old), cap)
            return None if new is None else str(new).encode()

        return await cas_update(self._kv, key, fn) is not None
