"""Catálogo de herramientas del orquestador, decisión del modelo y estado de una ejecución (TaskRun).

El modelo decide la siguiente acción con una tool call; el dominio la traduce a "delegar en un rol"
o "terminar" y lleva la cuenta de pasos (máximo 6 decisiones por tarea). Python puro y
determinista: el workflow de Dapr se reejecuta (replay) y debe obtener siempre lo mismo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from agentlib.domain.chat import Message, ToolSpec
from agentlib.domain.messages import Role

MAX_STEPS = 6
TOOL_ROLE: dict[str, Role] = {
    "dispatch_research": "research",
    "dispatch_analysis": "analysis",
    "dispatch_execution": "execution",
}
FINISH = "finish"
_INSTR = {"instructions": {"type": "string", "maxLength": 500}}
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "dispatch_research",
        "Ask the researcher agent to gather context from the knowledge base.",
        _INSTR,
        ("instructions",),
    ),
    ToolSpec(
        "dispatch_execution",
        "Ask the executor agent to run a CPU tool from its closed list.",
        _INSTR,
        ("instructions",),
    ),
    ToolSpec(
        "dispatch_analysis", "Ask the analyst agent to score the results so far.", _INSTR, ("instructions",)
    ),
    ToolSpec(
        "finish",
        "Finish the task with a short summary.",
        {"summary": {"type": "string", "maxLength": 500}},
        ("summary",),
    ),
)
SYSTEM_PROMPT = (
    "You are the orchestrator of an agent fleet. Decide the next action with exactly one tool call. "
    "Delegate research, then execution, then analysis, and call finish when the goal is covered. "
    f"You have at most {MAX_STEPS} decisions."
)


@dataclass(frozen=True)
class Decision:
    tool: str
    call_id: str
    args: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    note: str | None = None

    @property
    def role(self) -> Role | None:
        return TOOL_ROLE.get(self.tool)

    @property
    def finishes(self) -> bool:
        return self.role is None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Decision:
        return cls(
            str(d["tool"]),
            str(d["call_id"]),
            dict(d.get("args") or {}),
            bool(d.get("degraded")),
            d.get("note"),
        )


def decision_from_calls(
    calls: list[tuple[str, str, dict[str, Any]]], content: str | None, degraded: bool, step: int
) -> Decision:
    """Primera tool call conocida; sin tool call o con una desconocida → `finish`."""
    for call_id, name, args in calls:
        if name in TOOL_ROLE or name == FINISH:
            return Decision(name, call_id, args, degraded)
    unknown = calls[0][1] if calls else None
    note = (
        f"model requested unknown tool '{unknown}'" if unknown else (content or "model returned no tool call")
    )
    return Decision(FINISH, f"call_auto_{step}", {"summary": note[:300]}, degraded, note=note[:300])


@dataclass
class StepRecord:
    step: int
    tool: str
    call_id: str
    role: Role
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    agent: str | None = None
    pod: str | None = None


@dataclass
class TaskRun:
    task_id: str
    goal: str
    complexity: int
    mode: str
    created_at: float
    traceparent: str | None = None
    max_steps: int = MAX_STEPS
    decisions: int = 0
    steps: list[StepRecord] = field(default_factory=list)
    degraded: bool = False
    status: str = "running"
    finish_reason: str | None = None
    summary: str | None = None
    pending: Decision | None = None

    @classmethod
    def start(cls, inp: dict[str, Any]) -> TaskRun:
        return cls(
            task_id=str(inp["task_id"]),
            goal=str(inp["goal"]),
            complexity=int(inp.get("complexity", 3)),
            mode=str(inp.get("mode", "simulated")),
            created_at=float(inp.get("created_at", 0.0)),
            traceparent=inp.get("traceparent"),
            max_steps=int(inp.get("max_steps", MAX_STEPS)),
        )

    @property
    def done(self) -> bool:
        return self.status != "running"

    @property
    def step(self) -> int:
        return len(self.steps)

    def history(self) -> list[dict[str, Any]]:
        return [asdict(s) for s in self.steps]

    def decide_input(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "complexity": self.complexity,
            "mode": self.mode,
            "step": self.step,
            "history": self.history(),
            "traceparent": self.traceparent,
        }

    def apply_decision(self, decision: Decision) -> None:
        self.decisions += 1
        self.degraded = self.degraded or decision.degraded
        if decision.finishes:
            self._finish("completed", "finish", str(decision.args.get("summary") or decision.note or ""))
            return
        self.pending = decision

    def dispatch_input(self) -> dict[str, Any]:
        assert self.pending is not None and self.pending.role is not None
        return {
            "task_id": self.task_id,
            "step": self.step,
            "role": self.pending.role,
            "mode": self.mode,
            "goal": self.goal,
            "complexity": self.complexity,
            "args": self.pending.args,
            "context": self.history(),
            "traceparent": self.traceparent,
        }

    def apply_result(self, result: dict[str, Any] | None) -> None:
        """Registra la respuesta del agente (o `timeout` si es None) y aplica el límite de pasos."""
        assert self.pending is not None and self.pending.role is not None
        res = result or {}
        self.steps.append(
            StepRecord(
                step=self.step,
                tool=self.pending.tool,
                call_id=self.pending.call_id,
                role=self.pending.role,
                status=str(res.get("status", "timeout")) if result is not None else "timeout",
                result=dict(res.get("result") or {}),
                degraded=bool(res.get("degraded", False)),
                agent=res.get("agent"),
                pod=res.get("pod"),
            )
        )
        self.degraded = self.degraded or bool(res.get("degraded", False))
        self.pending = None
        if self.decisions >= self.max_steps:
            self._finish("completed", "step_limit", "step limit reached")

    def fail(self, reason: str) -> None:
        self._finish("failed", reason, reason)

    def _finish(self, status: str, reason: str, summary: str) -> None:
        self.status, self.finish_reason, self.summary = status, reason, summary[:500]

    def progress(self) -> dict[str, Any]:
        return {"steps": self.step, "decisions": self.decisions, "degraded": self.degraded, "mode": self.mode}

    def outcome(self) -> dict[str, Any]:
        evaluation = next(
            (s.result for s in reversed(self.steps) if s.role == "analysis" and s.status == "ok"), None
        )
        return {
            "task_id": self.task_id,
            "status": self.status,
            "mode": self.mode,
            "degraded": self.degraded,
            "finish_reason": self.finish_reason,
            "summary": self.summary,
            "steps": self.history(),
            "evaluation": evaluation,
            "created_at": self.created_at,
        }


def build_messages(goal: str, complexity: int, history: list[dict[str, Any]]) -> list[Message]:
    """Conversación para el modelo: objetivo + una pareja tool_call/tool por paso ya hecho."""
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"{goal}\ncomplexity={complexity}"},
    ]
    for h in history:
        call = {"id": h["call_id"], "type": "function", "function": {"name": h["tool"], "arguments": "{}"}}
        messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        payload = {"status": h["status"], "agent": h.get("agent"), "result": h.get("result")}
        messages.append(
            {"role": "tool", "tool_call_id": h["call_id"], "content": json.dumps(payload, default=str)[:1200]}
        )
    return messages
