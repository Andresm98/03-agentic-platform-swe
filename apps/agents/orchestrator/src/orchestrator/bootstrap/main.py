"""Composition root del orquestador: único sitio que conoce todas las capas.

Hay dos "lados" con event loops distintos y por tanto con instancias de cliente separadas:
- lado HTTP (loop de uvicorn): API pública, suscripción a `agent.*.completed`;
- lado workflow (loop propio del worker de durabletask): actividades decidir/delegar/completar.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from agentlib.adapters.inbound.dapr_subscription import (
    register_event_route,
    register_subscriptions,
    subscription,
)
from agentlib.adapters.inbound.http_app import create_app
from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics
from agentlib.adapters.outbound.system import SystemClock, Uuid7Generator
from agentlib.application.ports import EventPublisherPort, LLMPort
from agentlib.bootstrap.runtime import init_observability, make_llm, serve
from agentlib.bootstrap.settings import BaseSettings, env_bool, env_float, env_int, env_str
from orchestrator.adapters.inbound.http import register_routes
from orchestrator.adapters.outbound.dapr_workflow_engine import DaprWorkflowEngine
from orchestrator.adapters.outbound.metrics import PrometheusOrchestratorMetrics
from orchestrator.adapters.outbound.nats_queue_probe import NatsQueueProbe
from orchestrator.application.activities import (
    CompleteTask,
    DecideNextStep,
    DispatchToAgent,
    HandleAgentResult,
)
from orchestrator.application.ports import QueueProbePort, WorkflowEnginePort
from orchestrator.application.tasks import GetTask, SubmitTask
from orchestrator.domain.plan import MAX_STEPS
from orchestrator.domain.task import AdmissionPolicy, ShedPolicy

log = logging.getLogger(__name__)
COMPLETED_TOPIC = "agent.*.completed"  # una sola suscripción → un solo consumidor durable `orchestrator`


@dataclass(frozen=True)
class OrchestratorSettings(BaseSettings):
    demo_token: str = field(default_factory=lambda: env_str("DEMO_TOKEN", ""), repr=False)
    nats_monitor_url: str = field(default_factory=lambda: env_str("NATS_MONITOR_URL", ""))
    queue_shed_threshold: int = field(default_factory=lambda: env_int("QUEUE_SHED_THRESHOLD", 5000))
    max_body_bytes: int = field(default_factory=lambda: env_int("MAX_BODY_BYTES", 16384))
    step_timeout_s: float = field(default_factory=lambda: env_float("STEP_TIMEOUT_S", 120.0))
    max_steps: int = field(default_factory=lambda: env_int("MAX_STEPS", MAX_STEPS))
    workflow_enabled: bool = field(default_factory=lambda: env_bool("WORKFLOW_RUNTIME_ENABLED", True))


@dataclass
class Overrides:
    """Puertos sustituibles en tests (sin Dapr ni red)."""

    engine: WorkflowEnginePort | None = None
    queue: QueueProbePort | None = None
    publisher: EventPublisherPort | None = None
    llm: LLMPort | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _start_workflow_runtime(settings: OrchestratorSettings, metrics: FleetMetrics, ov: Overrides) -> Any:
    from dapr.ext.workflow import WorkflowRuntime

    from orchestrator.adapters.inbound.dapr_workflow import register

    wf_metrics = PrometheusOrchestratorMetrics(metrics)
    wf_publisher = ov.publisher or DaprPubSubPublisher(settings.dapr_http_endpoint, settings.pubsub_name)
    runtime = WorkflowRuntime()
    register(
        runtime,
        decide=DecideNextStep(ov.llm or make_llm(settings, "orchestrator"), wf_metrics),
        dispatch=DispatchToAgent(wf_publisher),
        complete=CompleteTask(wf_publisher, SystemClock(), wf_metrics),
        step_timeout_s=settings.step_timeout_s,
    )

    def start() -> None:
        try:
            runtime.start()  # type: ignore[no-untyped-call]
            log.info("workflow runtime started")
        except Exception:  # el worker sigue reintentando la conexión; readyz lo refleja
            log.warning("workflow runtime not ready yet", exc_info=True)

    threading.Thread(target=start, name="wf-start", daemon=True).start()
    return runtime


def build_app(settings: OrchestratorSettings | None = None, overrides: Overrides | None = None) -> FastAPI:
    settings = settings or OrchestratorSettings()
    ov = overrides or Overrides()
    metrics = init_observability(settings)
    o_metrics = PrometheusOrchestratorMetrics(metrics)
    sidecar = DaprPubSubPublisher(settings.dapr_http_endpoint, settings.pubsub_name)
    publisher = ov.publisher or sidecar
    engine = ov.engine or DaprWorkflowEngine()
    state: dict[str, Any] = {"runtime": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.workflow_enabled:
            state["runtime"] = _start_workflow_runtime(settings, metrics, ov)
        yield
        runtime = state["runtime"]
        if runtime is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(runtime.shutdown)

    app, readiness = create_app(
        title="orchestrator", metrics=metrics, pod_name=settings.pod_name, lifespan=lifespan
    )
    if ov.publisher is None:
        readiness.add("dapr", sidecar.healthy)

    async def workflow_ready() -> bool:
        runtime = state["runtime"]
        if not settings.workflow_enabled:
            return True
        return runtime is not None and await asyncio.to_thread(runtime.wait_for_worker_ready, 0.2)

    readiness.add("workflow", workflow_ready)

    submit = SubmitTask(
        admission=AdmissionPolicy(settings.demo_token),
        shed=ShedPolicy(threshold=settings.queue_shed_threshold),
        queue=ov.queue or NatsQueueProbe(settings.nats_monitor_url),
        publisher=publisher,
        engine=engine,
        ids=Uuid7Generator(),
        clock=SystemClock(),
        metrics=o_metrics,
        max_steps=settings.max_steps,
    )
    register_routes(app, submit, GetTask(engine), settings.max_body_bytes)
    handle_result = HandleAgentResult(engine)

    async def on_completed(data: Any, traceparent: str | None) -> str:
        return str(await handle_result(data, traceparent))

    register_subscriptions(
        app,
        [
            subscription(
                settings.pubsub_name, COMPLETED_TOPIC, "/events/agent-completed", settings.dead_letter_topic
            )
        ],
    )
    register_event_route(app, "/events/agent-completed", on_completed)
    return app


def main() -> None:
    settings = OrchestratorSettings()
    serve(build_app(settings), settings)
