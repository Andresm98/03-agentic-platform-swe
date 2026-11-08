"""Composition root de fake-llm."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import FastAPI

from agentlib.adapters.inbound.http_app import create_app
from agentlib.bootstrap.runtime import init_observability, serve
from agentlib.bootstrap.settings import BaseSettings, env_bool, env_float, env_int
from fake_llm.adapters.inbound.http import register_routes
from fake_llm.adapters.outbound.runtime import AsyncioSleeper, PrometheusFakeMetrics, SeededRandom, WallClock
from fake_llm.application.complete_chat import ClockPort, CompleteChat, FaultControl, RandomPort, SleeperPort
from fake_llm.domain.faults import FaultProfile


@dataclass(frozen=True)
class FakeSettings(BaseSettings):
    seed: int = field(default_factory=lambda: env_int("FAKE_SEED", 42))
    admin_enabled: bool = field(default_factory=lambda: env_bool("FAKE_ADMIN_ENABLED", True))
    profile: FaultProfile = field(
        default_factory=lambda: FaultProfile(
            error_rate_429=env_float("FAKE_ERROR_RATE_429", 0.0),
            error_rate_500=env_float("FAKE_ERROR_RATE_500", 0.0),
            timeout_rate=env_float("FAKE_TIMEOUT_RATE", 0.0),
            timeout_s=env_float("FAKE_TIMEOUT_S", 60.0),
            latency_median_ms=env_float("FAKE_LATENCY_MEDIAN_MS", 300.0),
            latency_sigma=env_float("FAKE_LATENCY_SIGMA", 0.5),
            latency_max_ms=env_float("FAKE_LATENCY_MAX_MS", 5000.0),
        )
    )


def build_app(
    settings: FakeSettings | None = None,
    *,
    rng: RandomPort | None = None,
    sleeper: SleeperPort | None = None,
    clock: ClockPort | None = None,
) -> FastAPI:
    settings = settings or FakeSettings()
    metrics = init_observability(settings)
    faults = FaultControl(settings.profile)
    complete = CompleteChat(
        faults=faults,
        rng=rng or SeededRandom(settings.seed),
        sleeper=sleeper or AsyncioSleeper(),
        clock=clock or WallClock(),
        metrics=PrometheusFakeMetrics(metrics.registry),
    )
    app, _ = create_app(title="fake-llm", metrics=metrics, pod_name=settings.pod_name)
    register_routes(app, complete, faults, settings.admin_enabled)
    return app


def main() -> None:
    settings = FakeSettings()
    serve(build_app(settings), settings)
