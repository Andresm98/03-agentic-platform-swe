"""Puntuación determinista del resultado de una tarea (sustituye al *evaluator* del brief)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PASS_THRESHOLD = 60


@dataclass(frozen=True)
class Evaluation:
    score: int
    verdict: str
    breakdown: dict[str, int]
    degraded_inputs: bool
    evidence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "verdict": self.verdict,
            "breakdown": dict(self.breakdown),
            "degraded_inputs": self.degraded_inputs,
            "evidence": self.evidence,
        }


def _results(items: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    return [i for i in items if i.get("role") == role]


def score(context: list[dict[str, Any]], goal: str) -> Evaluation:
    """0..100: investigación con hallazgos (30), ejecución correcta (40), fiabilidad (20), objetivo (10)."""
    hits = sum(int((r.get("result") or {}).get("hits", 0)) for r in _results(context, "research"))
    executed = [
        e
        for e in _results(context, "execution")
        if e.get("status") == "ok" and "error" not in (e.get("result") or {})
    ]
    errors = sum(1 for item in context if item.get("status") != "ok")
    breakdown = {
        "research": min(30, 10 * hits),
        "execution": 40 if executed else 0,
        "reliability": max(0, 20 - 10 * errors),
        "goal": 10 if goal.strip() else 0,
    }
    total = sum(breakdown.values())
    return Evaluation(
        score=total,
        verdict="pass" if total >= PASS_THRESHOLD else "fail",
        breakdown=breakdown,
        degraded_inputs=any(bool(i.get("degraded")) for i in context),
        evidence=len(context),
    )
