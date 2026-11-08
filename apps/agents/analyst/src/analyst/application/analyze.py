"""Caso de uso Analyze: puntúa sin llamar al modelo y publica `tasks.evaluated`."""

from __future__ import annotations

from agentlib.application.handle_request import WorkOutput
from agentlib.application.ports import EventPublisherPort
from agentlib.domain.messages import AgentRequest, message_id
from analyst.domain.scoring import score

EVALUATED_TOPIC = "tasks.evaluated"


class Analyze:
    def __init__(self, publisher: EventPublisherPort) -> None:
        self._publisher = publisher

    async def __call__(self, req: AgentRequest) -> WorkOutput:
        evaluation = score(req.context, req.goal).to_dict()
        await self._publisher.publish(
            EVALUATED_TOPIC,
            {"task_id": req.task_id, "mode": req.mode, **evaluation},
            msg_id=message_id(req.task_id, req.step, EVALUATED_TOPIC),
            traceparent=req.traceparent,
        )
        return WorkOutput(evaluation)
