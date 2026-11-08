"""Construcción de respuestas con la forma exacta de la API de OpenAI (chat.completion y error)."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class ChatValidationError(ValueError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4)) if text else 0


def validate(body: Any) -> tuple[str, list[dict[str, Any]], int]:
    if not isinstance(body, dict):
        raise ChatValidationError("body must be a JSON object", "invalid_body")
    model = body.get("model")
    messages = body.get("messages")
    if not isinstance(model, str) or not model:
        raise ChatValidationError("you must provide a model parameter", "missing_model")
    if not isinstance(messages, list) or not messages or not all(isinstance(m, dict) for m in messages):
        raise ChatValidationError("messages must be a non-empty array of objects", "missing_messages")
    max_tokens = body.get("max_tokens")
    if max_tokens is None:
        max_tokens = body.get("max_completion_tokens", 1024)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        raise ChatValidationError("max_tokens must be a positive integer", "invalid_max_tokens")
    return model, messages, max_tokens


def error_body(message: str, etype: str, code: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": etype, "param": None, "code": code}}


def completion(
    *,
    body: dict[str, Any],
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    content: str | None,
    tool_calls: list[dict[str, Any]],
    created: int,
) -> dict[str, Any]:
    if content is not None and tokens(content) > max_tokens:
        content = content[: max_tokens * 4]
    prompt_tokens = tokens(json.dumps(messages, ensure_ascii=False, default=str))
    completion_tokens = min(
        max_tokens, tokens(content or "") + sum(tokens(json.dumps(tc)) for tc in tool_calls)
    )
    message: dict[str, Any] = {"role": "assistant", "content": content, "refusal": None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return {
        "id": f"chatcmpl-{digest[:24]}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "system_fingerprint": "fake-llm",
        "choices": [
            {
                "index": 0,
                "message": message,
                "logprobs": None,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
