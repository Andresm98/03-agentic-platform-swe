"""Adaptador de `CpuRunnerPort`: `ProcessPoolExecutor(max_workers=1)`.

IMPLEMENTATION_PLAN §1.1.11: el trabajo de CPU en el event loop o en un hilo (GIL) bloquearía
`/healthz` y los probes fallarían bajo carga. Un único proceso hijo por réplica: la réplica
consume ~1 vCPU como máximo y el HPA por CPU (60 % del request) ve la carga real.
Contexto `spawn`: evita `fork` con hilos (gRPC/OTel) en el padre.
"""

from __future__ import annotations

import asyncio
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from executor.domain.tools import run_tool


class ProcessPoolCpuRunner:
    def __init__(self, min_duration_ms: int = 0) -> None:
        self._min_ms = min_duration_ms
        self._pool: ProcessPoolExecutor | None = None

    def _get(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        return self._pool

    async def run(self, name: str, complexity: int) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._get(), run_tool, name, complexity, self._min_ms)

    def shutdown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
