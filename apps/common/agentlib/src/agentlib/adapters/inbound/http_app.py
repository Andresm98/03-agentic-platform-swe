"""Adaptador HTTP común: FastAPI con health, readiness, métricas y cabecera `X-Pod-Name`.

- `/healthz` (liveness): el proceso responde; no depende de nada externo para no provocar
  reinicios en cascada si cae NATS o el sidecar.
- `/readyz` (readiness): todas las comprobaciones registradas pasan.
- `/metrics`: registro Prometheus propio del servicio.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from agentlib.adapters.outbound.prometheus_metrics import FleetMetrics

ReadinessCheck = Callable[[], Awaitable[bool]]
_UNTRACKED = {"/metrics", "/healthz", "/readyz"}


class Readiness:
    def __init__(self) -> None:
        self._checks: dict[str, ReadinessCheck] = {}
        self.draining = False

    def add(self, name: str, check: ReadinessCheck) -> None:
        self._checks[name] = check

    async def evaluate(self) -> tuple[bool, dict[str, bool]]:
        results: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                results[name] = bool(await asyncio.wait_for(check(), timeout=2.0))
            except Exception:  # cualquier fallo de una comprobación = no listo
                results[name] = False
        return all(results.values()) and not self.draining, results


def _install_middlewares(app: FastAPI, metrics: FleetMetrics, pod_name: str) -> None:
    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Pod-Name"] = pod_name
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            if route not in _UNTRACKED:
                metrics.http_duration.labels(request.method, route, str(status)).observe(
                    time.perf_counter() - start
                )


def _install_probes(app: FastAPI, metrics: FleetMetrics, readiness: Readiness) -> None:
    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> Response:
        ok, checks = await readiness.evaluate()
        return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus() -> Response:
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)


def create_app(
    *,
    title: str,
    metrics: FleetMetrics,
    pod_name: str,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> tuple[FastAPI, Readiness]:
    readiness = Readiness()

    async def _noop(_: FastAPI) -> AsyncIterator[None]:
        yield

    from contextlib import asynccontextmanager

    app = FastAPI(
        title=title,
        lifespan=lifespan or asynccontextmanager(_noop),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    _install_middlewares(app, metrics, pod_name)
    _install_probes(app, metrics, readiness)
    return app, readiness
