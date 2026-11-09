"""Composition root del gateway: único sitio que conoce todas las capas."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from agentlib.adapters.inbound.http_app import create_app
from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics
from agentlib.bootstrap.runtime import init_observability, serve
from llm_gateway.adapters.inbound.http import register_routes
from llm_gateway.adapters.outbound.http_upstream import HttpUpstream
from llm_gateway.adapters.outbound.kv import NatsConnection
from llm_gateway.adapters.outbound.langsmith_telemetry import LangSmithTelemetry, NoopTelemetry
from llm_gateway.adapters.outbound.metrics import (
    AsyncioSleeper,
    MonotonicClock,
    PrometheusGatewayMetrics,
    SystemRandom,
)
from llm_gateway.application.budget_service import BudgetService
from llm_gateway.application.ports import KeyValuePort, LLMTelemetryPort, UpstreamPort
from llm_gateway.application.route_completion import RetryConfig, RouteCompletion
from llm_gateway.bootstrap.settings import GatewaySettings
from llm_gateway.domain.budget import BudgetLimits, ModelPrice
from llm_gateway.domain.circuit import CircuitConfig
from llm_gateway.domain.routing import RoutingPolicy, TelemetrySampling

log = logging.getLogger(__name__)


def make_telemetry(settings: GatewaySettings, metrics: FleetMetrics) -> LLMTelemetryPort:
    if not settings.langsmith_enabled:
        return NoopTelemetry()
    if not settings.langsmith_api_key:
        log.warning("LANGSMITH_ENABLED=true but LANGSMITH_API_KEY is empty: LangSmith export disabled")
        return NoopTelemetry()
    return LangSmithTelemetry(
        endpoint=settings.langsmith_endpoint,
        api_key=settings.langsmith_api_key,
        project=settings.langsmith_project,
        agent_id=settings.langsmith_agent_id,
        agent_environment=settings.langsmith_agent_environment,
        on_error=lambda: metrics.telemetry_errors.labels("langsmith").inc(),
        on_success=lambda n: metrics.telemetry_exported.labels("langsmith", "any").inc(n),
    )


def make_use_case(
    settings: GatewaySettings,
    metrics: FleetMetrics,
    kv: KeyValuePort,
    upstream: UpstreamPort,
    telemetry: LLMTelemetryPort,
    **overrides: Any,
) -> RouteCompletion:
    policy = RoutingPolicy(
        global_mode="live" if settings.global_mode == "live" else "simulated",
        has_api_key=bool(settings.openai_api_key),
        max_input_tokens=settings.max_input_tokens,
        agent_max_tokens={k: int(v) for k, v in settings.agent_max_tokens.items()},
        prices={
            m: ModelPrice(float(p["input_usd_per_1m"]), float(p["output_usd_per_1m"]))
            for m, p in settings.allowed_models.items()
        },
    )
    limits = BudgetLimits(
        limit_usd=settings.budget_usd,
        live_tasks_per_minute=settings.live_tasks_per_minute,
        live_tasks_total=settings.live_tasks_total,
        task_max_llm_calls=settings.task_max_llm_calls,
        task_max_tokens=settings.task_max_tokens,
    )
    deps: dict[str, Any] = {
        "clock": MonotonicClock(),
        "sleeper": AsyncioSleeper(),
        "rng": SystemRandom(),
        **overrides,
    }
    return RouteCompletion(
        policy=policy,
        budget=BudgetService(kv, limits),
        upstream=upstream,
        metrics=PrometheusGatewayMetrics(metrics),
        telemetry=telemetry,
        sampling=TelemetrySampling(settings.langsmith_simulated_sample_rate),
        circuit=CircuitConfig(
            settings.circuit_failure_threshold, settings.circuit_window_s, settings.circuit_open_s
        ),
        retry=RetryConfig(retries=settings.upstream_retries),
        **deps,
    )


@dataclass
class _Holder:
    use_case: RouteCompletion | None = None


def build_app(
    settings: GatewaySettings | None = None,
    *,
    kv: KeyValuePort | None = None,
    upstream: UpstreamPort | None = None,
    telemetry: LLMTelemetryPort | None = None,
    **overrides: Any,
) -> FastAPI:
    settings = settings or GatewaySettings()
    metrics = init_observability(settings)
    upstream = upstream or HttpUpstream(
        openai_base_url=settings.openai_base_url,
        openai_api_key=settings.openai_api_key,
        fake_base_url=settings.fake_llm_url,
        timeout_s=settings.upstream_timeout_s,
    )
    tele = telemetry or make_telemetry(settings, metrics)
    nats = NatsConnection(
        settings.nats_url,
        settings.nats_user,
        settings.nats_password,
        settings.budget_bucket,
        settings.service_name,
    )
    holder = _Holder()

    async def connect_and_refresh() -> None:
        store = kv
        if store is None:
            store = await _connect_with_retry(nats)
        holder.use_case = make_use_case(settings, metrics, store, upstream, tele, **overrides)
        while True:
            await holder.use_case.refresh_budget()
            await asyncio.sleep(15)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # NATS en segundo plano: /healthz responde desde el primer segundo y /readyz da 503 hasta tener el KV.
        task = asyncio.create_task(connect_and_refresh())
        log.info(
            "gateway starting",
            extra={"global_mode": settings.global_mode, "live_key": bool(settings.openai_api_key)},
        )
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await nats.close()
        if hasattr(tele, "shutdown"):
            tele.shutdown()

    app, readiness = create_app(
        title="llm-gateway", metrics=metrics, pod_name=settings.pod_name, lifespan=lifespan
    )

    async def ready() -> bool:
        return holder.use_case is not None and (kv is not None or nats.connected)

    readiness.add("budget_store", ready)
    info = {"limit_usd": settings.budget_usd, "global_mode": settings.global_mode}
    register_routes(app, lambda: holder.use_case, list(settings.allowed_models), info)
    return app


async def _connect_with_retry(nats: NatsConnection) -> KeyValuePort:
    delay = 1.0
    while True:
        try:
            return await nats.connect()
        except Exception as exc:  # reintento indefinido con backoff; readyz = 503 mientras
            log.warning("nats not available yet", extra={"error": str(exc)[:200], "retry_in_s": delay})
            await asyncio.sleep(delay)
            delay = min(delay * 2, 15.0)


def main() -> None:
    settings = GatewaySettings()
    serve(build_app(settings), settings)
