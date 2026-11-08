"""Value objects de una conversación con el modelo y recorte de contexto (≤ 2.000 tokens)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

Message = dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatRequest:
    messages: list[Message]
    task_id: str
    mode: str
    tools: tuple[ToolSpec, ...] = ()
    traceparent: str | None = None


@dataclass(frozen=True)
class ChatResult:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    mode: str = "simulated"
    degraded: bool = False
    reason: str | None = None
    message: Message = field(default_factory=dict)


def estimate_tokens(messages: list[Message]) -> int:
    """Estimación barata (~4 caracteres por token): suficiente para recortar y presupuestar."""
    return max(1, len(json.dumps(messages, ensure_ascii=False, default=str)) // 4)


def _group_turns(tail: list[Message]) -> list[list[Message]]:
    groups: list[list[Message]] = []
    for m in tail:
        if m.get("role") == "tool" and groups:
            groups[-1].append(m)
        else:
            groups.append([m])
    return groups


def trim_messages(messages: list[Message], max_tokens: int) -> list[Message]:
    """Conserva system + primer usuario y descarta los turnos más antiguos.

    Un `tool` se descarta junto al `assistant` que lo originó: la API rechaza `tool_call_id`
    huérfanos.
    """
    if estimate_tokens(messages) <= max_tokens:
        return messages
    head = [m for m in messages[:2] if m.get("role") in ("system", "user")]
    groups = _group_turns(messages[len(head) :])
    while groups and estimate_tokens(head + [m for g in groups for m in g]) > max_tokens:
        groups.pop(0)
    trimmed = head + [m for g in groups for m in g]
    if estimate_tokens(trimmed) <= max_tokens:
        return trimmed
    budget_chars = max(16, max_tokens * 4 // (2 * max(1, len(trimmed))))
    return [
        {**m, "content": m["content"][:budget_chars]} if isinstance(m.get("content"), str) else m
        for m in trimmed
    ]
