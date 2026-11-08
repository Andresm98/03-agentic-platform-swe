"""Adaptador de `EventPublisherPort` sobre la API HTTP del sidecar Dapr.

- `POST /v1.0/publish/<pubsub>/<topic>?metadata.cloudevent.id=<id>`: el componente
  `pubsub.jetstream` usa el `id` del CloudEvent como `Nats-Msg-Id` (verificado en el código de
  components-contrib `pubsub/jetstream/jetstream.go`). TODO(verify): override de `cloudevent.id`
  vía metadata en daprd 1.19.1 (docker compose lo ejercita).
- Se usa la API HTTP con httpx (asíncrona, testeable con un transporte simulado) en lugar del
  cliente gRPC del SDK, que bloquea el arranque esperando al sidecar. El Workflow sí usa el SDK.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from agentlib.domain.errors import PublishRejectedError


class DaprPubSubPublisher:
    def __init__(self, endpoint: str, pubsub_name: str, client: httpx.AsyncClient | None = None) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._pubsub = pubsub_name
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))

    async def publish(
        self, topic: str, data: dict[str, Any], *, msg_id: str, traceparent: str | None = None
    ) -> None:
        headers = {"content-type": "application/json"}
        if traceparent:
            headers["traceparent"] = traceparent
        url = f"{self._endpoint}/v1.0/publish/{self._pubsub}/{topic}"
        try:
            resp = await self._client.post(
                url,
                content=json.dumps(data, default=str),
                headers=headers,
                params={"metadata.cloudevent.id": msg_id},
            )
        except httpx.HTTPError as exc:
            raise PublishRejectedError(f"dapr publish transport error: {type(exc).__name__}") from exc
        if resp.status_code >= 300:
            raise PublishRejectedError(f"dapr publish {topic} failed: {resp.status_code} {resp.text[:200]}")

    async def healthy(self) -> bool:
        try:
            resp = await self._client.get(f"{self._endpoint}/v1.0/healthz/outbound")
        except httpx.HTTPError:
            return False
        return resp.status_code in (200, 204)

    async def aclose(self) -> None:
        await self._client.aclose()
