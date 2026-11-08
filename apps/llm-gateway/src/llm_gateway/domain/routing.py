"""Política de enrutado: validación de la petición, tope de tokens y modo efectivo. Python puro.

El modo lo decide la arquitectura (ADR-0002 §6), nunca el cliente final:
    live ⇐ X-Task-Mode=live (solo lo pone el orquestador tras validar X-Demo-Token)
           ∧ LLM_GLOBAL_MODE=live ∧ hay API key ∧ límites de tarea ∧ tareas live/min y total
           ∧ presupuesto reservado ∧ circuito `openai` cerrado
    si no ⇒ fake-llm; una tarea live servida por fake-llm queda `degraded=true` + motivo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from llm_gateway.domain.budget import ModelPrice

Mode = Literal["live", "simulated"]
DROPPED_FIELDS = ("max_completion_tokens", "n", "stream", "user")


class RequestRejectedError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class RoutingPolicy:
    global_mode: Mode = "simulated"
    has_api_key: bool = False
    max_input_tokens: int = 2000
    agent_max_tokens: dict[str, int] = field(default_factory=lambda: {"orchestrator": 300, "default": 200})
    prices: dict[str, ModelPrice] = field(default_factory=dict)

    def cap_for(self, agent: str) -> int:
        return int(self.agent_max_tokens.get(agent, self.agent_max_tokens.get("default", 200)))

    def price(self, model: str) -> ModelPrice:
        return self.prices[model]


@dataclass(frozen=True)
class PreparedRequest:
    body: dict[str, Any]
    model: str
    input_tokens: int
    max_tokens: int


def estimate_tokens(messages: list[Any]) -> int:
    return max(1, len(json.dumps(messages, ensure_ascii=False, default=str)) // 4)


def prepare(body: Any, agent: str, policy: RoutingPolicy) -> PreparedRequest:
    """Valida y normaliza: modelo permitido, contexto ≤ máximo, `max_tokens` recortado al tope."""
    if not isinstance(body, dict):
        raise RequestRejectedError(400, "invalid_body", "body must be a JSON object")
    if body.get("stream"):
        raise RequestRejectedError(400, "stream_unsupported", "streaming is not supported by the lab gateway")
    model = body.get("model")
    if not isinstance(model, str) or model not in policy.prices:
        raise RequestRejectedError(400, "model_not_allowed", f"model '{model}' is not in the allowed list")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RequestRejectedError(400, "missing_messages", "messages must be a non-empty array")
    in_tokens = estimate_tokens(messages)
    if in_tokens > policy.max_input_tokens:
        raise RequestRejectedError(
            400, "context_length_exceeded", f"input of ~{in_tokens} tokens exceeds {policy.max_input_tokens}"
        )
    requested = body.get("max_tokens")
    if requested is None:
        requested = body.get("max_completion_tokens")
    if requested is None:
        requested = policy.cap_for(agent)
    if not isinstance(requested, int) or requested < 1:
        raise RequestRejectedError(400, "invalid_max_tokens", "max_tokens must be a positive integer")
    clean = {k: v for k, v in body.items() if k not in DROPPED_FIELDS}
    clean["max_tokens"] = min(requested, policy.cap_for(agent))
    return PreparedRequest(clean, model, in_tokens, clean["max_tokens"])


def live_precondition(policy: RoutingPolicy, requested_live: bool, task_id: str) -> str | None:
    """Motivo por el que una llamada no puede ir a live antes de tocar el presupuesto (o None)."""
    if not requested_live:
        return "not_requested"
    if policy.global_mode != "live":
        return "global_simulated"
    if not policy.has_api_key:
        return "no_api_key"
    if not task_id:
        return "missing_task_id"
    return None


@dataclass(frozen=True)
class TelemetrySampling:
    """Llamadas live al 100 %; simuladas con `simulated_rate` (cuota gratuita de LangSmith)."""

    simulated_rate: float = 0.01

    def should_export(self, mode: Mode, roll: float) -> bool:
        return mode == "live" or roll < self.simulated_rate
