"""Adaptador de `LLMTelemetryPort` hacia LangSmith por OTLP (sin LangChain, LangGraph ni el SDK).

Verificado en la documentación de LangSmith (consultada el 2026-11-07): ingesta OpenTelemetry en
`https://api.smith.langchain.com/otel` con cabecera `x-api-key`; los exporters añaden
`/v1/traces`. Los spans usan las convenciones GenAI (`gen_ai.*`) que LangSmith interpreta.
TODO(verify): nombre exacto de la cabecera de proyecto (`Langsmith-Project`) y el mapeo de
`langsmith.metadata.*` en la UI, con una traza real de la demo live.

Diseño fail-open y no bloqueante:
- `TracerProvider` PROPIO (no el global): estas trazas no se mezclan con las de Alloy/Tempo.
- `record()` solo crea y cierra un span en memoria; el envío lo hace el `BatchSpanProcessor` en
  su hilo. Si la cola se llena, descarta. Si LangSmith falla o va lento, la llamada al modelo ya
  respondió: solo sube `llm_telemetry_export_errors_total{exporter="langsmith"}`.
- No participa en readiness.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from llm_gateway.application.ports import LLMCallRecord

log = logging.getLogger(__name__)
_MAX_CHARS = 2000


class CountingExporter(SpanExporter):
    """Delegado que cuenta los fallos de exportación sin propagarlos."""

    def __init__(
        self, inner: SpanExporter, on_error: Callable[[], None], on_success: Callable[[int], None]
    ) -> None:
        self._inner = inner
        self._on_error = on_error
        self._on_success = on_success

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._inner.export(spans)
        except Exception:  # fail-open: nunca se propaga
            self._on_error()
            return SpanExportResult.FAILURE
        if result is SpanExportResult.SUCCESS:
            self._on_success(len(spans))
        else:
            self._on_error()
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def span_attributes(call: LLMCallRecord) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "langsmith.span.kind": "llm",
        "gen_ai.system": "openai" if call.mode == "live" else "fake-llm",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": call.model,
        "gen_ai.response.model": call.model,
        "gen_ai.request.max_tokens": call.max_tokens,
        "gen_ai.usage.input_tokens": call.prompt_tokens,
        "gen_ai.usage.output_tokens": call.completion_tokens,
        "langsmith.metadata.task_id": call.task_id,
        "langsmith.metadata.agent": call.agent,
        "langsmith.metadata.mode": call.mode,
        "langsmith.metadata.degraded": call.degraded,
        "langsmith.metadata.cost_usd": call.cost_usd,
    }
    if call.reason:
        attrs["langsmith.metadata.degraded_reason"] = call.reason
    for i, msg in enumerate(call.request_messages[-8:]):
        attrs[f"gen_ai.prompt.{i}.role"] = str(msg.get("role", ""))
        attrs[f"gen_ai.prompt.{i}.content"] = str(msg.get("content") or "")[:_MAX_CHARS]
    attrs["gen_ai.completion.0.role"] = "assistant"
    content = call.response_message.get("content")
    if content is None and call.response_message.get("tool_calls"):
        content = str(call.response_message["tool_calls"])
    attrs["gen_ai.completion.0.content"] = str(content or "")[:_MAX_CHARS]
    return attrs


class LangSmithTelemetry:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        project: str,
        on_error: Callable[[], None],
        on_success: Callable[[int], None],
        exporter: SpanExporter | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        inner = exporter or OTLPSpanExporter(
            endpoint=f"{endpoint.rstrip('/')}/v1/traces",
            headers={"x-api-key": api_key, "Langsmith-Project": project},
            timeout=timeout_s,
        )
        self._on_error = on_error
        self._provider = TracerProvider(resource=Resource.create({"service.name": "llm-gateway"}))
        self._provider.add_span_processor(
            BatchSpanProcessor(
                CountingExporter(inner, on_error, on_success), max_queue_size=2048, schedule_delay_millis=2000
            )
        )
        self._tracer = self._provider.get_tracer("llm-gateway.langsmith")

    def record(self, call: LLMCallRecord) -> None:
        try:
            span = self._tracer.start_span(
                f"llm.{call.agent}", start_time=int(call.start_s * 1e9), attributes=span_attributes(call)
            )
            span.end(end_time=int(call.end_s * 1e9))
        except Exception:  # fail-open
            self._on_error()
            log.debug("langsmith record failed", exc_info=True)

    def shutdown(self) -> None:
        try:
            self._provider.shutdown()
        except Exception:
            log.debug("langsmith shutdown failed", exc_info=True)


class NoopTelemetry:
    def record(self, call: LLMCallRecord) -> None:
        return None

    def shutdown(self) -> None:
        return None
