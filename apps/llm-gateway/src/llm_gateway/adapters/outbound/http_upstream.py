"""Adaptador de `UpstreamPort`: HTTP a OpenAI (con la API key) o a fake-llm.

La API key solo se añade hacia OpenAI; a fake-llm viajan `X-Agent` y `traceparent`. Hacia OpenAI
no se envían cabeceras internas.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from llm_gateway.application.ports import Upstream, UpstreamFailureError


class HttpUpstream:
    def __init__(
        self,
        *,
        openai_base_url: str,
        openai_api_key: str,
        fake_base_url: str,
        timeout_s: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._urls = {"openai": openai_base_url.rstrip("/"), "fake": fake_base_url.rstrip("/")}
        self._key = openai_api_key
        self._timeout = timeout_s
        self._client = client or httpx.AsyncClient(limits=httpx.Limits(max_connections=200))

    def _headers(self, upstream: Upstream, extra: dict[str, str]) -> dict[str, str]:
        if upstream == "openai":
            return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json", **extra}

    async def chat(self, upstream: Upstream, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        url = f"{self._urls[upstream]}/chat/completions"
        try:
            resp = await self._client.post(
                url, content=json.dumps(body), headers=self._headers(upstream, headers), timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise UpstreamFailureError(0, type(exc).__name__) from exc
        if resp.status_code >= 300:
            raise UpstreamFailureError(resp.status_code, f"status {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise UpstreamFailureError(502, "invalid JSON from upstream") from exc
        if not isinstance(data, dict):
            raise UpstreamFailureError(502, "unexpected upstream payload")
        return data

    async def aclose(self) -> None:
        await self._client.aclose()
