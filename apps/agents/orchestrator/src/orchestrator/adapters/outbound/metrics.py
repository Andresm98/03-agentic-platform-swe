"""Adaptador Prometheus de `OrchestratorMetricsPort`."""

from __future__ import annotations

from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics


class PrometheusOrchestratorMetrics:
    def __init__(self, metrics: FleetMetrics) -> None:
        self._m = metrics

    def shed(self, reason: str) -> None:
        self._m.tasks_shed.labels(reason).inc()

    def admission(self, mode: str, token: str) -> None:
        self._m.admissions.labels(mode, token).inc()

    def task_finished(self, mode: str, status: str, seconds: float) -> None:
        self._m.task_e2e.labels(mode, status).observe(seconds)
        self._m.tasks_processed.labels("orchestrator", status).inc()

    def agent_step(self, agent: str) -> None:
        self._m.agent_steps.labels(agent).inc()
