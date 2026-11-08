"""Piezas comunes del composition root: logging, trazas, LLM, publisher, worker HTTP y uvicorn."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from agentlib.adapters.inbound.dapr_subscription import (
    register_event_route,
    register_subscriptions,
    subscription,
)
from agentlib.adapters.inbound.http_app import Readiness, create_app
from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.adapters.outbound.json_logging import configure_logging
from agentlib.adapters.outbound.openai_llm import OpenAIGatewayLLM
from agentlib.adapters.outbound.otel import setup_tracing
from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics, PrometheusAgentMetrics
from agentlib.application.handle_request import AgentWork, HandleAgentRequest
from agentlib.bootstrap.settings import BaseSettings
from agentlib.domain.messages import Role, requested_topic


def init_observability(settings: BaseSettings) -> FleetMetrics:
    configure_logging(settings.service_name, settings.log_level)
    setup_tracing(
        settings.service_name, settings.otel_endpoint, settings.otel_enabled, settings.otel_sample_ratio
    )
    return FleetMetrics()


def make_llm(settings: BaseSettings, agent: str) -> OpenAIGatewayLLM:
    return OpenAIGatewayLLM(
        agent=agent,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        timeout_s=settings.llm_timeout_s,
        max_input_tokens=settings.llm_max_input_tokens,
    )


@dataclass
class WorkerApp:
    app: FastAPI
    readiness: Readiness


def build_worker_app(
    settings: BaseSettings,
    *,
    role: Role,
    work: AgentWork,
    metrics: FleetMetrics,
    publisher: DaprPubSubPublisher,
    lifespan: Any = None,
) -> WorkerApp:
    """Ensambla un agente trabajador: suscripción a `agent.<rol>.requested` → caso de uso."""
    app, readiness = create_app(
        title=settings.service_name, metrics=metrics, pod_name=settings.pod_name, lifespan=lifespan
    )
    readiness.add("dapr", publisher.healthy)
    use_case = HandleAgentRequest(
        agent=settings.service_name,
        pod=settings.pod_name,
        work=work,
        publisher=publisher,
        metrics=PrometheusAgentMetrics(metrics),
    )
    register_subscriptions(
        app,
        [
            subscription(
                settings.pubsub_name, requested_topic(role), "/events/requested", settings.dead_letter_topic
            )
        ],
    )

    async def handler(data: Any, traceparent: str | None) -> str:
        return str(await use_case(data, traceparent))

    register_event_route(app, "/events/requested", handler)
    return WorkerApp(app, readiness)


def serve(app: FastAPI, settings: BaseSettings) -> None:
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104 - escucha en el pod; la exposición la controla NetworkPolicy
        port=settings.port,
        log_config=None,
        access_log=False,
        timeout_graceful_shutdown=settings.graceful_timeout_s,
    )


LifespanFactory = AbstractAsyncContextManager[None]
