"""OpenTelemetry: trazas OTLP hacia Alloy y propagación W3C `traceparent`.

Dapr genera los spans de pub/sub y workflow; las apps añaden los suyos. Con `OTEL_ENABLED=false`
el tracer es no-op, pero la propagación de `traceparent` sigue funcionando.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.trace import Span


def setup_tracing(service_name: str, endpoint: str, enabled: bool, sample_ratio: float = 1.0) -> bool:
    """Instala el TracerProvider global de OTel (la API de OTel es global por diseño)."""
    if not enabled:
        return False
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, "service.namespace": "agentic-platform"}),
        sampler=ParentBased(TraceIdRatioBased(sample_ratio)),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    return True


def inject_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier.get("traceparent")


class OtelTracer:
    """Implementa `TracerPort`."""

    def __init__(self, name: str) -> None:
        self._tracer = trace.get_tracer(name)

    @contextlib.contextmanager
    def span(self, name: str, traceparent: str | None, attributes: dict[str, Any]) -> Iterator[Span]:
        ctx = propagate.extract({"traceparent": traceparent}) if traceparent else None
        with self._tracer.start_as_current_span(name, context=ctx, attributes=attributes) as sp:
            yield sp
