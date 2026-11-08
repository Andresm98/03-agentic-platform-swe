"""Adaptador de `QueueProbePort`: profundidad del stream `TASKS` vía el endpoint de monitorización
de NATS (`/jsz?streams=true`, el mismo que usa KEDA). Caché corta para no consultar en cada POST.
Si no hay URL configurada o NATS no responde, devuelve None (no se descarta nada por error).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)


def stream_messages(jsz: dict[str, Any], stream: str) -> int | None:
    for account in jsz.get("account_details") or []:
        for detail in account.get("stream_detail") or []:
            if detail.get("name") == stream:
                return int((detail.get("state") or {}).get("messages", 0))
    return None


class NatsQueueProbe:
    def __init__(
        self,
        monitor_url: str,
        stream: str = "TASKS",
        ttl_s: float = 2.0,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = monitor_url.rstrip("/")
        self._stream = stream
        self._ttl = ttl_s
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(1.0))
        self._clock = clock
        self._cached: tuple[float, int | None] = (-1e9, None)

    async def depth(self) -> int | None:
        if not self._url:
            return None
        at, value = self._cached
        if self._clock() - at < self._ttl:
            return value
        try:
            resp = await self._client.get(f"{self._url}/jsz", params={"streams": "true", "accounts": "true"})
            value = stream_messages(resp.json(), self._stream) if resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            log.debug("nats monitor unavailable", exc_info=True)
            value = None
        self._cached = (self._clock(), value)
        return value
