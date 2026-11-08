"""Caso de uso común de los agentes trabajadores: procesar `agent.<rol>.requested`.

Semántica de entrega (ADR-0002 §6):
- mensaje inválido → `DROP` (reintentar no sirve);
- dependencia caída (gateway, sidecar) → `RETRY`: el sidecar aplica Resiliency y, agotada,
  reenvía a la DLQ `tasks.dead`;
- error de negocio → se publica `status=error` para que el orquestador decida.
La respuesta se publica con id determinista → `Nats-Msg-Id` (sin duplicados en reintentos).
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass
from typing import Any, Protocol

from agentlib.application.ports import AgentMetricsPort, EventPublisherPort
from agentlib.domain.errors import InvalidMessageError, TransientDependencyError
from agentlib.domain.messages import AgentRequest, AgentResult, completed_topic, message_id


class Outcome(enum.StrEnum):
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    DROP = "DROP"


@dataclass(frozen=True)
class WorkOutput:
    result: dict[str, Any]
    degraded: bool = False
    llm_calls: int = 0


class AgentWork(Protocol):
    """Trabajo específico de cada agente (investigar, analizar, ejecutar)."""

    async def __call__(self, request: AgentRequest, /) -> WorkOutput: ...


class HandleAgentRequest:
    def __init__(
        self,
        *,
        agent: str,
        pod: str,
        work: AgentWork,
        publisher: EventPublisherPort,
        metrics: AgentMetricsPort,
    ) -> None:
        self._agent = agent
        self._pod = pod
        self._work = work
        self._publisher = publisher
        self._metrics = metrics

    async def __call__(self, payload: Any, traceparent: str | None) -> Outcome:
        try:
            req = AgentRequest.from_dict(payload)
        except InvalidMessageError:
            self._metrics.message_processed(self._agent, "invalid")
            return Outcome.DROP
        start = time.perf_counter()
        req = AgentRequest(**{**req.to_dict(), "traceparent": traceparent or req.traceparent})
        try:
            out = await self._work(req)
            status = "ok"
        except TransientDependencyError:
            self._metrics.message_processed(self._agent, "retry")
            return Outcome.RETRY
        except Exception as exc:  # error de negocio: se informa, no se reintenta
            out, status = WorkOutput({"error": f"{type(exc).__name__}: {str(exc)[:300]}"}), "error"
        result = AgentResult(
            task_id=req.task_id,
            step=req.step,
            role=req.role,
            agent=self._agent,
            status=status,  # type: ignore[arg-type]
            result=out.result,
            degraded=out.degraded,
            llm_calls=out.llm_calls,
            pod=self._pod,
        )
        topic = completed_topic(req.role)
        try:
            await self._publisher.publish(
                topic,
                result.to_dict(),
                msg_id=message_id(req.task_id, req.step, topic),
                traceparent=req.traceparent,
            )
        except TransientDependencyError:
            self._metrics.message_processed(self._agent, "retry")
            return Outcome.RETRY
        self._metrics.message_processed(self._agent, status, time.perf_counter() - start)
        return Outcome.SUCCESS
