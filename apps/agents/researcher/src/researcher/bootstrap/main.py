"""Composition root del investigador."""

from __future__ import annotations

from fastapi import FastAPI

from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.adapters.outbound.prometheus_metrics import PrometheusAgentMetrics
from agentlib.application.ports import LLMPort
from agentlib.bootstrap.runtime import build_worker_app, init_observability, make_llm, serve
from agentlib.bootstrap.settings import BaseSettings, env_int
from researcher.adapters.outbound.json_knowledge import PackagedKnowledge
from researcher.application.research import Research


def build_app(
    settings: BaseSettings | None = None,
    *,
    llm: LLMPort | None = None,
    publisher: DaprPubSubPublisher | None = None,
) -> FastAPI:
    settings = settings or BaseSettings()
    metrics = init_observability(settings)
    work = Research(
        llm or make_llm(settings, "researcher"),
        PrometheusAgentMetrics(metrics),
        PackagedKnowledge().load(),
        max_llm_calls=env_int("AGENT_MAX_LLM_CALLS", 1),
    )
    pub = publisher or DaprPubSubPublisher(settings.dapr_http_endpoint, settings.pubsub_name)
    return build_worker_app(settings, role="research", work=work, metrics=metrics, publisher=pub).app


def main() -> None:
    settings = BaseSettings()
    serve(build_app(settings), settings)
