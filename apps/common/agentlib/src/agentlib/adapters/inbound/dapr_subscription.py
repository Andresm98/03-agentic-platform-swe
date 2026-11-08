"""Adaptador de entrada Dapr pub/sub: suscripción programática y entrega a un caso de uso.

`GET /dapr/subscribe` declara el topic, la ruta y `deadLetterTopic: tasks.dead`. El sidecar
entrega un CloudEvent; aquí se desenvuelve y el caso de uso devuelve SUCCESS/RETRY/DROP, que es
exactamente el contrato de respuesta de Dapr.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request

from agentlib.adapters.outbound.json_logging import bind_task

Handler = Callable[[Any, str | None], Awaitable[str]]


def unwrap_cloudevent(body: Any) -> tuple[Any, str | None]:
    if not isinstance(body, dict):
        return body, None
    data = body.get("data", body)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            data = {"raw": data}
    tp = body.get("traceparent")
    return data, tp if isinstance(tp, str) else None


def subscription(pubsub: str, topic: str, route: str, dead_letter: str | None) -> dict[str, Any]:
    sub: dict[str, Any] = {"pubsubname": pubsub, "topic": topic, "route": route}
    if dead_letter:
        sub["deadLetterTopic"] = dead_letter
    return sub


def register_subscriptions(app: FastAPI, subscriptions: list[dict[str, Any]]) -> None:
    @app.get("/dapr/subscribe", include_in_schema=False)
    async def dapr_subscribe() -> list[dict[str, Any]]:
        return subscriptions


def register_event_route(app: FastAPI, route: str, handler: Handler) -> None:
    async def on_event(request: Request) -> dict[str, str]:
        try:
            body = await request.json()
        except ValueError:
            return {"status": "DROP"}
        data, ce_tp = unwrap_cloudevent(body)
        task_id = data.get("task_id") if isinstance(data, dict) else None
        with bind_task(task_id if isinstance(task_id, str) else None):
            outcome = await handler(data, request.headers.get("traceparent") or ce_tp)
        return {"status": str(outcome)}

    app.add_api_route(route, on_event, methods=["POST"], include_in_schema=False)
