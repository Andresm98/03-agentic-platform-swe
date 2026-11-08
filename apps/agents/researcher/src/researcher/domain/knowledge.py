"""Base de conocimiento local y búsqueda determinista (sin búsqueda web: coste cero)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class Document:
    id: str
    topic: str
    keywords: frozenset[str]
    text: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Document:
        return cls(
            str(d["id"]), str(d["topic"]).lower(), frozenset(k.lower() for k in d["keywords"]), str(d["text"])
        )


class KnowledgeBase:
    def __init__(self, documents: list[Document]) -> None:
        self._docs = documents

    def __len__(self) -> int:
        return len(self._docs)

    def search(self, topic: str, goal: str = "", limit: int = 3) -> dict[str, Any]:
        """Puntuación: 2 por keyword que coincide con tema u objetivo, +3 si el tema es exacto."""
        terms = {t.lower() for t in _TOKEN.findall(f"{topic} {goal}")}
        scored = []
        for doc in self._docs:
            score = 2 * len(terms & doc.keywords) + (3 if topic.lower() == doc.topic else 0)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        hits = [
            {"id": d.id, "topic": d.topic, "text": d.text, "score": s} for s, d in scored[: max(1, limit)]
        ]
        return {"topic": topic, "hits": len(hits), "documents": hits}
