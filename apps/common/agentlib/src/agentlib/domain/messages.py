"""Mensajes de la flota (CONTRACTS §7). Python puro: validación explícita, sin pydantic.

Correlación siempre por `task_id`. Topics: `agent.<rol>.requested|completed`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast

from agentlib.domain.errors import InvalidMessageError

Role = Literal["research", "analysis", "execution"]
Mode = Literal["live", "simulated"]
ResultStatus = Literal["ok", "error"]

ROLES: tuple[Role, ...] = ("research", "analysis", "execution")
MODES: tuple[Mode, ...] = ("live", "simulated")
ROLE_AGENT: dict[Role, str] = {"research": "researcher", "analysis": "analyst", "execution": "executor"}
MAX_GOAL_CHARS = 4000
DEAD_LETTER_TOPIC = "tasks.dead"


def requested_topic(role: Role) -> str:
    return f"agent.{role}.requested"


def completed_topic(role: Role) -> str:
    return f"agent.{role}.completed"


def result_event_name(step: int) -> str:
    """Nombre del evento externo que espera el workflow para la respuesta del paso `step`."""
    return f"agent_result_{step}"


def message_id(task_id: str, step: int, topic: str) -> str:
    """Id determinista → `Nats-Msg-Id`: un reintento no duplica el mensaje en JetStream."""
    return f"{task_id}:{step}:{topic}"


def _req(data: dict[str, Any], key: str, kind: type) -> Any:
    value = data.get(key)
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is int):
        raise InvalidMessageError(f"field '{key}' must be {kind.__name__}")
    return value


def _int_in(data: dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise InvalidMessageError(f"field '{key}' must be an int in [{lo}, {hi}]")
    return value


def _choice(data: dict[str, Any], key: str, options: tuple[str, ...], default: str | None = None) -> str:
    value = data.get(key, default)
    if value not in options:
        raise InvalidMessageError(f"field '{key}' must be one of {options}")
    return cast(str, value)


@dataclass(frozen=True)
class AgentRequest:
    task_id: str
    step: int
    role: Role
    goal: str
    mode: Mode = "simulated"
    complexity: int = 3
    args: dict[str, Any] = field(default_factory=dict)
    context: list[dict[str, Any]] = field(default_factory=list)
    traceparent: str | None = None

    @classmethod
    def from_dict(cls, data: Any) -> AgentRequest:
        if not isinstance(data, dict):
            raise InvalidMessageError("request must be an object")
        goal = _req(data, "goal", str)
        if len(goal) > MAX_GOAL_CHARS:
            raise InvalidMessageError("goal too long")
        args = data.get("args", {})
        context = data.get("context", [])
        if args is None:
            args = {}
        if context is None:
            context = []
        if not isinstance(args, dict) or not isinstance(context, list):
            raise InvalidMessageError("args must be an object and context a list")
        tp = data.get("traceparent")
        return cls(
            task_id=_req(data, "task_id", str),
            step=_int_in(data, "step", -1, 0, 32),
            role=cast(Role, _choice(data, "role", ROLES)),
            goal=goal,
            mode=cast(Mode, _choice(data, "mode", MODES, "simulated")),
            complexity=_int_in(data, "complexity", 3, 1, 10),
            args=args,
            context=[c for c in context if isinstance(c, dict)],
            traceparent=tp if isinstance(tp, str) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentResult:
    task_id: str
    step: int
    role: Role
    agent: str
    status: ResultStatus = "ok"
    result: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    llm_calls: int = 0
    pod: str | None = None

    @classmethod
    def from_dict(cls, data: Any) -> AgentResult:
        if not isinstance(data, dict):
            raise InvalidMessageError("result must be an object")
        result = data.get("result") or {}
        pod = data.get("pod")
        return cls(
            task_id=_req(data, "task_id", str),
            step=_int_in(data, "step", -1, 0, 32),
            role=cast(Role, _choice(data, "role", ROLES)),
            agent=_req(data, "agent", str),
            status=cast(ResultStatus, _choice(data, "status", ("ok", "error"), "ok")),
            result=result if isinstance(result, dict) else {"value": result},
            degraded=bool(data.get("degraded", False)),
            llm_calls=_int_in(data, "llm_calls", 0, 0, 100),
            pod=pod if isinstance(pod, str) else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
