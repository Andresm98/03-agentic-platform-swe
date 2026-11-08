"""Caso de uso RouteCompletion: decide live/simulated, aplica presupuesto, reintentos y circuito."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from llm_gateway.application.budget_service import BudgetService, ContentionError
from llm_gateway.application.ports import (
    ClockPort,
    GatewayMetricsPort,
    LLMCallRecord,
    LLMTelemetryPort,
    RandomPort,
    SleeperPort,
    Upstream,
    UpstreamFailureError,
    UpstreamPort,
)
from llm_gateway.domain.circuit import CircuitBreaker, CircuitConfig
from llm_gateway.domain.routing import (
    Mode,
    PreparedRequest,
    RequestRejectedError,
    RoutingPolicy,
    TelemetrySampling,
    live_precondition,
    prepare,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallContext:
    agent: str
    task_id: str
    requested_live: bool
    traceparent: str | None = None

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> CallContext:
        h = {k.lower(): v for k, v in headers.items()}
        return cls(
            agent=h.get("x-agent", "unknown")[:40],
            task_id=h.get("x-task-id", "")[:64],
            requested_live=h.get("x-task-mode", "simulated").lower() == "live",
            traceparent=h.get("traceparent"),
        )


@dataclass(frozen=True)
class RouteResult:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RetryConfig:
    retries: int = 2
    base_backoff_s: float = 0.2


def _error(
    status: int, code: str, message: str, etype: str = "invalid_request_error", **hdrs: str
) -> RouteResult:
    return RouteResult(
        status, {"error": {"message": message, "type": etype, "param": None, "code": code}}, dict(hdrs)
    )


@dataclass
class _Live:
    ok: bool
    reason: str | None = None
    reserved: int = 0


class RouteCompletion:
    def __init__(
        self,
        *,
        policy: RoutingPolicy,
        budget: BudgetService,
        upstream: UpstreamPort,
        metrics: GatewayMetricsPort,
        telemetry: LLMTelemetryPort,
        sampling: TelemetrySampling,
        clock: ClockPort,
        sleeper: SleeperPort,
        rng: RandomPort,
        circuit: CircuitConfig,
        retry: RetryConfig,
    ) -> None:
        self._policy = policy
        self._budget = budget
        self._upstream = upstream
        self._metrics = metrics
        self._telemetry = telemetry
        self._sampling = sampling
        self._clock = clock
        self._sleeper = sleeper
        self._rng = rng
        self._retry = retry
        self.circuits: dict[Upstream, CircuitBreaker] = {
            name: CircuitBreaker(name, circuit, clock.now, metrics.circuit) for name in ("openai", "fake")
        }

    async def __call__(self, body: Any, headers: dict[str, str]) -> RouteResult:
        ctx = CallContext.from_headers(headers)
        start = self._clock.now()
        try:
            req = prepare(body, ctx.agent, self._policy)
        except RequestRejectedError as exc:
            self._metrics.request(ctx.agent, "rejected", "-", exc.code)
            return _error(exc.status, exc.code, str(exc))
        reason: str | None = None
        if ctx.requested_live:
            result, reason = await self._try_live(ctx, req, start)
            if result is not None:
                return result
        return await self._simulated(ctx, req, start, degraded=ctx.requested_live, reason=reason)

    # ------------------------------------------------------------------ live
    async def _try_live(
        self, ctx: CallContext, req: PreparedRequest, start: float
    ) -> tuple[RouteResult | None, str | None]:
        live = await self._admit_live(ctx, req)
        if not live.ok:
            return None, live.reason
        try:
            data = await self._call("openai", req.body, ctx)
        except UpstreamFailureError as exc:
            await self._budget.reconcile(live.reserved, 0)
            log.warning(
                "openai failed, degrading to fake-llm", extra={"status": exc.status, "agent": ctx.agent}
            )
            return None, "upstream_error"
        usage = data.get("usage") or {}
        actual = self._policy.price(req.model).cost_micro(
            int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        )
        await self._budget.reconcile(live.reserved, actual)
        self._metrics.cost(ctx.agent, req.model, actual / 1_000_000)
        await self.refresh_budget()
        return self._ok(
            data, ctx, req, "live", start, degraded=False, reason=None, cost=actual / 1_000_000
        ), None

    async def _admit_live(self, ctx: CallContext, req: PreparedRequest) -> _Live:
        pre = live_precondition(self._policy, ctx.requested_live, ctx.task_id)
        if pre is not None:
            return _Live(False, pre)
        try:
            adm = await self._budget.admit_task_call(
                ctx.task_id, int(self._clock.now() // 60), req.input_tokens + req.max_tokens
            )
            if not adm.ok:
                return _Live(False, adm.reason)
            reserved = self._policy.price(req.model).cost_micro(req.input_tokens, req.max_tokens)
            adm = await self._budget.reserve(reserved)
        except ContentionError:
            return _Live(False, "budget_contention")
        if not adm.ok:
            await self.refresh_budget()
            return _Live(False, adm.reason)
        if not self.circuits["openai"].allow():
            await self._budget.reconcile(reserved, 0)
            return _Live(False, "circuit_open")
        return _Live(True, reserved=reserved)

    # ------------------------------------------------------------------ simulated
    async def _simulated(
        self, ctx: CallContext, req: PreparedRequest, start: float, *, degraded: bool, reason: str | None
    ) -> RouteResult:
        if not self.circuits["fake"].allow():
            self._metrics.request(ctx.agent, "simulated", req.model, "circuit_open")
            return _error(
                503, "circuit_open", "simulated upstream circuit open", "server_error", **{"Retry-After": "2"}
            )
        try:
            data = await self._call("fake", req.body, ctx)
        except UpstreamFailureError as exc:
            self._metrics.request(ctx.agent, "simulated", req.model, "error")
            return _error(
                503,
                "upstream_unavailable",
                f"simulated upstream failed: {exc}",
                "server_error",
                **{"Retry-After": "2"},
            )
        return self._ok(data, ctx, req, "simulated", start, degraded=degraded, reason=reason)

    # ------------------------------------------------------------------ upstream con reintentos
    async def _call(self, upstream: Upstream, body: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
        circuit = self.circuits[upstream]
        headers = {"X-Agent": ctx.agent}
        if ctx.traceparent:
            headers["traceparent"] = ctx.traceparent
        last = UpstreamFailureError(0, "no attempt")
        for attempt in range(self._retry.retries + 1):
            try:
                data = await self._upstream.chat(upstream, body, headers)
            except UpstreamFailureError as exc:
                last = exc
                if not exc.retryable:
                    raise  # error de contrato (4xx): no cuenta para el circuito
                circuit.record_failure()
                if attempt >= self._retry.retries or not circuit.allow():
                    break
                await self._sleeper.sleep(self._rng.random() * self._retry.base_backoff_s * 2**attempt)
                continue
            circuit.record_success()
            return data
        raise last

    # ------------------------------------------------------------------ salida
    def _ok(
        self,
        data: dict[str, Any],
        ctx: CallContext,
        req: PreparedRequest,
        mode: Mode,
        start: float,
        *,
        degraded: bool,
        reason: str | None,
        cost: float = 0.0,
    ) -> RouteResult:
        usage = data.get("usage") or {}
        prompt, completion = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        self._metrics.tokens(ctx.agent, mode, prompt, completion)
        self._metrics.request(ctx.agent, mode, req.model, "degraded" if degraded else "ok")
        self._export(data, ctx, req, mode, start, degraded, reason, cost, prompt, completion)
        data["x_gateway"] = {"mode": mode, "degraded": degraded, "reason": reason}
        headers = {"X-LLM-Mode": mode, "X-LLM-Degraded": str(degraded).lower()}
        if reason:
            headers["X-LLM-Reason"] = reason
        return RouteResult(200, data, headers)

    def _export(
        self,
        data: dict[str, Any],
        ctx: CallContext,
        req: PreparedRequest,
        mode: Mode,
        start: float,
        degraded: bool,
        reason: str | None,
        cost: float,
        prompt: int,
        completion: int,
    ) -> None:
        if not self._sampling.should_export(mode, self._rng.random()):
            return
        choices = data.get("choices") or [{}]
        message = choices[0].get("message") or {}
        try:
            self._record(
                LLMCallRecord(
                    agent=ctx.agent,
                    task_id=ctx.task_id,
                    mode=mode,
                    model=req.model,
                    degraded=degraded,
                    reason=reason,
                    request_messages=req.body.get("messages", []),
                    response_message=message,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    max_tokens=req.max_tokens,
                    start_s=start,
                    end_s=self._clock.now(),
                    cost_usd=cost,
                    tool_names=[t.get("function", {}).get("name", "") for t in req.body.get("tools") or []],
                )
            )
        except Exception:  # fail-open: la telemetría nunca rompe una llamada al modelo
            log.debug("llm telemetry record failed", exc_info=True)

    def _record(self, call: LLMCallRecord) -> None:
        self._telemetry.record(call)

    async def budget_remaining(self) -> float:
        return await self._budget.remaining_usd()

    async def refresh_budget(self) -> None:
        try:
            self._metrics.budget_remaining(await self._budget.remaining_usd())
        except Exception:  # la métrica nunca rompe una petición
            log.debug("budget gauge refresh failed", exc_info=True)
