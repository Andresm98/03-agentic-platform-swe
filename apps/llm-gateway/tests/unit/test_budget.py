"""Presupuesto: políticas puras y servicio CAS sobre KV en memoria."""

from __future__ import annotations

import asyncio

import pytest
from fakes import YieldingKV

from llm_gateway.adapters.outbound.kv import InMemoryKeyValue
from llm_gateway.application.budget_service import BudgetService
from llm_gateway.domain.budget import (
    BudgetLimits,
    ModelPrice,
    TaskUsage,
    admit_task_call,
    incremented,
    next_spent,
    reconciled,
    usd_to_micro,
)


def test_cost_in_micro_usd_rounds_up() -> None:
    price = ModelPrice(0.15, 0.60)
    assert price.cost_micro(1_000_000, 0) == 150_000  # 0.15 USD
    assert price.cost_micro(1, 1) == 1  # 0.75 micro-USD → 1
    assert usd_to_micro(3.0) == 3_000_000


def test_pure_transitions() -> None:
    assert next_spent(100, 50, 200) == 150
    assert next_spent(180, 50, 200) is None
    assert reconciled(150, 50, 20) == 120
    assert reconciled(10, 50, 0) == 0
    assert incremented(4, 5) == 5
    assert incremented(5, 5) is None


def test_task_limits_steps_and_tokens() -> None:
    limits = BudgetLimits(task_max_llm_calls=6, task_max_tokens=1000)
    usage, adm = admit_task_call(TaskUsage(), limits, 100)
    assert adm.ok and adm.first_call and usage == TaskUsage(1, 100)
    _, adm = admit_task_call(TaskUsage(6, 100), limits, 1)
    assert not adm.ok and adm.reason == "task_step_limit"
    _, adm = admit_task_call(TaskUsage(1, 950), limits, 100)
    assert not adm.ok and adm.reason == "task_token_limit"
    assert TaskUsage.decode(TaskUsage(2, 30).encode()) == TaskUsage(2, 30)


async def test_reserve_until_exhausted_then_reconcile_releases() -> None:
    svc = BudgetService(InMemoryKeyValue(), BudgetLimits(limit_usd=0.001))  # 1000 micro-USD
    assert (await svc.reserve(600)).ok
    denied = await svc.reserve(600)
    assert not denied.ok and denied.reason == "budget_exhausted"
    await svc.reconcile(600, 100)  # coste real menor que lo reservado
    assert await svc.remaining_usd() == pytest.approx(0.0009)
    assert (await svc.reserve(600)).ok


async def test_concurrent_reservations_never_exceed_limit() -> None:
    svc = BudgetService(YieldingKV(), BudgetLimits(limit_usd=0.001))
    results = await asyncio.gather(*(svc.reserve(100) for _ in range(30)))
    assert sum(r.ok for r in results) == 10
    assert await svc.remaining_usd() == 0


async def test_live_tasks_per_minute_and_total() -> None:
    svc = BudgetService(InMemoryKeyValue(), BudgetLimits(live_tasks_per_minute=5, live_tasks_total=7))
    minute = [await svc.admit_task_call(f"t{i}", 100, 10) for i in range(6)]
    assert [a.ok for a in minute] == [True] * 5 + [False]
    assert minute[-1].reason == "live_rate_limit"
    # La 2.ª llamada de una tarea ya admitida no consume cupo de tareas.
    assert (await svc.admit_task_call("t0", 100, 10)).ok
    nxt = [await svc.admit_task_call(f"u{i}", 101, 10) for i in range(3)]
    assert [a.ok for a in nxt] == [True, True, False]
    assert nxt[-1].reason == "live_total_limit"


async def test_task_step_limit_is_six_calls() -> None:
    svc = BudgetService(InMemoryKeyValue(), BudgetLimits())
    results = [await svc.admit_task_call("t", 1, 10) for _ in range(7)]
    assert [r.ok for r in results] == [True] * 6 + [False]
    assert results[-1].reason == "task_step_limit"
