"""Métricas Prometheus de la flota (IMPLEMENTATION_PLAN §5, ADR-0002 §6).

Los nombres y labels se definen una sola vez aquí. Los objetos `Counter`/`Histogram` viven en un
`CollectorRegistry` propio que crea el composition root (sin registro global por defecto), y cada
servicio usa los que le corresponden a través de sus puertos de métricas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


@dataclass
class FleetMetrics:
    registry: CollectorRegistry = field(default_factory=lambda: CollectorRegistry(auto_describe=True))

    def __post_init__(self) -> None:
        r = self.registry
        self.http_duration = Histogram(
            "http_request_duration_seconds",
            "Duración de las peticiones HTTP",
            ["method", "route", "status"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
            registry=r,
        )
        self.tasks_processed = Counter(
            "tasks_processed_total", "Mensajes o tareas procesadas", ["agent", "status"], registry=r
        )
        self.task_processing = Histogram(
            "task_processing_seconds",
            "Procesamiento de un mensaje por agente",
            ["agent"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
            registry=r,
        )
        self.task_e2e = Histogram(
            "task_e2e_latency_seconds",
            "Latencia de extremo a extremo de una tarea",
            ["mode", "status"],
            buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
            registry=r,
        )
        self.agent_steps = Counter(
            "agent_steps_total", "Pasos de agente (llamadas al modelo)", ["agent"], registry=r
        )
        self.llm_requests = Counter(
            "llm_requests_total",
            "Llamadas al modelo vía gateway",
            ["agent", "mode", "model", "outcome"],
            registry=r,
        )
        self.llm_tokens = Counter(
            "llm_tokens_total", "Tokens consumidos", ["agent", "mode", "direction"], registry=r
        )
        self.llm_budget_remaining = Gauge(
            "llm_budget_remaining", "Presupuesto LLM restante (USD)", registry=r
        )
        self.llm_circuit_state = Gauge(
            "llm_circuit_state", "Circuito: 0 cerrado, 1 semiabierto, 2 abierto", ["upstream"], registry=r
        )
        self.llm_cost = Counter(
            "llm_cost_usd_total", "Coste live conciliado (USD)", ["agent", "model"], registry=r
        )
        self.tasks_shed = Counter(
            "tasks_shed_total", "Tareas rechazadas (backpressure)", ["reason"], registry=r
        )
        self.admissions = Counter("task_admissions_total", "Admisión por modo", ["mode", "token"], registry=r)
        self.telemetry_errors = Counter(
            "llm_telemetry_export_errors_total", "Fallos al exportar telemetría LLM", ["exporter"], registry=r
        )
        self.telemetry_exported = Counter(
            "llm_telemetry_exported_total",
            "Llamadas exportadas a la telemetría LLM",
            ["exporter", "mode"],
            registry=r,
        )


class PrometheusAgentMetrics:
    """Implementa `AgentMetricsPort`."""

    def __init__(self, metrics: FleetMetrics) -> None:
        self._m = metrics

    def message_processed(self, agent: str, status: str, seconds: float | None = None) -> None:
        self._m.tasks_processed.labels(agent, status).inc()
        if seconds is not None:
            self._m.task_processing.labels(agent).observe(seconds)

    def agent_step(self, agent: str) -> None:
        self._m.agent_steps.labels(agent).inc()
