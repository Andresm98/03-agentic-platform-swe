"""Composition root del agente de análisis."""

from __future__ import annotations

from fastapi import FastAPI

from agentlib.adapters.outbound.dapr_pubsub import DaprPubSubPublisher
from agentlib.bootstrap.runtime import build_worker_app, init_observability, serve
from agentlib.bootstrap.settings import BaseSettings
from analyst.application.analyze import Analyze


def build_app(
    settings: BaseSettings | None = None, *, publisher: DaprPubSubPublisher | None = None
) -> FastAPI:
    settings = settings or BaseSettings()
    metrics = init_observability(settings)
    pub = publisher or DaprPubSubPublisher(settings.dapr_http_endpoint, settings.pubsub_name)
    return build_worker_app(settings, role="analysis", work=Analyze(pub), metrics=metrics, publisher=pub).app


def main() -> None:
    settings = BaseSettings()
    serve(build_app(settings), settings)
