"""Adaptador de `LLMPort`: SDK oficial `openai` con `base_url` → `llm-gateway`.

- Ningún agente tiene la API key: se envía un marcador y el gateway lo ignora.
- Cabeceras de control: `X-Agent`, `X-Task-Id`, `X-Task-Mode` y `traceparent` (W3C).
- El gateway añade al cuerpo `x_gateway` ({mode, degraded, reason}); los modelos del SDK admiten
  campos extra (`model_config.extra = "allow"`, comprobado en openai 3.46.0).
- `max_retries=0`: los reintentos con jitter y el circuit breaker viven en el gateway.
"""

from __future__ import annotations

import json
from typing import Any

import openai
from openai import AsyncOpenAI

from agentlib.adapters.outbound.otel import inject_traceparent
from agentlib.domain.chat import ChatRequest, ChatResult, ToolCall, trim_messages
from agentlib.domain.errors import TransientDependencyError

_PLACEHOLDER_KEY = "gateway-holds-the-key"
_TRANSIENT = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
)


def _parse_calls(msg: Any) -> tuple[tuple[ToolCall, ...], list[dict[str, Any]]]:
    calls: list[ToolCall] = []
    raw: list[dict[str, Any]] = []
    for tc in msg.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_raw": tc.function.arguments}
        calls.append(
            ToolCall(id=tc.id, name=tc.function.name, arguments=args if isinstance(args, dict) else {})
        )
        raw.append(
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
        )
    return tuple(calls), raw


def parse_completion(completion: Any) -> ChatResult:
    msg = completion.choices[0].message
    calls, raw = _parse_calls(msg)
    extra = (getattr(completion, "model_extra", None) or {}).get("x_gateway") or {}
    usage = completion.usage
    message: dict[str, Any] = {"role": "assistant", "content": msg.content}
    if raw:
        message["tool_calls"] = raw
    return ChatResult(
        content=msg.content,
        tool_calls=calls,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        model=completion.model,
        mode=str(extra.get("mode", "simulated")),
        degraded=bool(extra.get("degraded", False)),
        reason=extra.get("reason"),
        message=message,
    )


class OpenAIGatewayLLM:
    def __init__(
        self,
        *,
        agent: str,
        base_url: str,
        model: str,
        max_tokens: int,
        timeout_s: float = 30.0,
        max_input_tokens: int = 2000,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._agent = agent
        self._model = model
        self._max_tokens = max_tokens
        self._max_input_tokens = max_input_tokens
        self._client = client or AsyncOpenAI(
            base_url=base_url, api_key=_PLACEHOLDER_KEY, timeout=timeout_s, max_retries=0
        )

    @property
    def agent(self) -> str:
        return self._agent

    def _kwargs(self, req: ChatRequest) -> dict[str, Any]:
        headers = {"X-Agent": self._agent, "X-Task-Id": req.task_id, "X-Task-Mode": req.mode}
        tp = req.traceparent or inject_traceparent()
        if tp:
            headers["traceparent"] = tp
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": trim_messages(req.messages, self._max_input_tokens),
            "max_tokens": self._max_tokens,
            "extra_headers": headers,
        }
        if req.tools:
            kwargs["tools"] = [t.to_openai() for t in req.tools]
            kwargs["tool_choice"] = "auto"
        return kwargs

    async def complete(self, request: ChatRequest) -> ChatResult:
        try:
            completion = await self._client.chat.completions.create(**self._kwargs(request))
        except _TRANSIENT as exc:
            raise TransientDependencyError(f"llm-gateway unavailable: {type(exc).__name__}") from exc
        return parse_completion(completion)
