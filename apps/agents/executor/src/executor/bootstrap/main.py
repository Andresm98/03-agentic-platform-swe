"""Composition root del agente de ejecución."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.adapters.outbound.prometheus_metrics import PrometheusAgentMetrics
from agentlib.application.ports import LLMPort
from agentlib.bootstrap.runtime import build_worker_app, init_observability, make_llm, serve
from agentlib.bootstrap.settings import BaseSettings, env_int
from executor.adapters.outbound.process_pool import ProcessPoolCpuRunner
from executor.application.execute import CpuRunnerPort, Execute


def build_app(
    settings: BaseSettings | None = None,
    *,
    llm: LLMPort | None = None,
    publisher: DaprPubSubPublisher | None = None,
    runner: CpuRunnerPort | None = None,
) -> FastAPI:
    settings = settings or BaseSettings()
    metrics = init_observability(settings)
    pool = ProcessPoolCpuRunner(min_duration_ms=env_int("WORK_DURATION_MS", 0))
    work = Execute(
        llm or make_llm(settings, "executor"),
        PrometheusAgentMetrics(metrics),
        runner or pool,
        max_llm_calls=env_int("AGENT_MAX_LLM_CALLS", 1),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        pool.shutdown()

    pub = publisher or DaprPubSubPublisher(settings.dapr_http_endpoint, settings.pubsub_name)
    return build_worker_app(
        settings, role="execution", work=work, metrics=metrics, publisher=pub, lifespan=lifespan
    ).app


def main() -> None:
    settings = BaseSettings()
    serve(build_app(settings), settings)
