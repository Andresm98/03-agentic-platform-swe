"""Adaptador LangSmith (OTLP): atributos GenAI, exportación en segundo plano y fail-open."""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from llm_gateway.adapters.outbound.langsmith_telemetry import (
    CountingExporter,
    LangSmithTelemetry,
    NoopTelemetry,
)
from llm_gateway.application.ports import LLMCallRecord

RECORD = LLMCallRecord(
    agent="orchestrator",
    task_id="0190-task",
    mode="live",
    model="gpt-4o-mini",
    degraded=False,
    reason=None,
    request_messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "goal"}],
    response_message={"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
    prompt_tokens=10,
    completion_tokens=5,
    max_tokens=300,
    start_s=1.0,
    end_s=2.0,
    cost_usd=0.0001,
)


class Counters:
    def __init__(self) -> None:
        self.errors = 0
        self.ok = 0

    def err(self) -> None:
        self.errors += 1

    def good(self, n: int) -> None:
        self.ok += n


class BrokenExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise ConnectionError("langsmith down")

    def shutdown(self) -> None:
        return None


def test_exports_genai_span_with_task_metadata() -> None:
    mem, c = InMemorySpanExporter(), Counters()
    tele = LangSmithTelemetry(
        endpoint="https://example.invalid/otel",
        api_key="k",
        project="p",
        on_error=c.err,
        on_success=c.good,
        exporter=mem,
    )
    tele.record(RECORD)
    tele.shutdown()  # vacía la cola del BatchSpanProcessor
    (span,) = mem.get_finished_spans()
    attrs = dict(span.attributes or {})
    assert span.name == "llm.orchestrator"
    assert attrs["gen_ai.request.model"] == "gpt-4o-mini" and attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["langsmith.metadata.task_id"] == "0190-task" and attrs["gen_ai.prompt.1.content"] == "goal"
    assert "c1" in str(attrs["gen_ai.completion.0.content"])
    assert span.end_time - span.start_time == 1_000_000_000
    assert c.ok == 1 and c.errors == 0


def test_export_failure_is_counted_and_never_raises() -> None:
    c = Counters()
    tele = LangSmithTelemetry(
        endpoint="https://example.invalid/otel",
        api_key="k",
        project="p",
        on_error=c.err,
        on_success=c.good,
        exporter=BrokenExporter(),
    )
    tele.record(RECORD)  # no lanza aunque el exportador esté caído
    tele.shutdown()
    assert c.errors >= 1 and c.ok == 0


def test_counting_exporter_failure_result() -> None:
    c = Counters()

    class Failing(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            return SpanExportResult.FAILURE

        def shutdown(self) -> None:
            return None

    assert CountingExporter(Failing(), c.err, c.good).export([]) is SpanExportResult.FAILURE
    assert c.errors == 1


def test_record_with_bad_data_is_fail_open() -> None:
    c = Counters()
    tele = LangSmithTelemetry(
        endpoint="https://example.invalid/otel",
        api_key="k",
        project="p",
        on_error=c.err,
        on_success=c.good,
        exporter=InMemorySpanExporter(),
    )
    bad = LLMCallRecord(**{**RECORD.__dict__, "start_s": float("nan")})
    tele.record(bad)
    tele.shutdown()
    assert c.errors == 1
    NoopTelemetry().record(RECORD)
