"""Repositorio de conocimiento: JSON versionado dentro de la imagen (`data/knowledge.json`)."""

from __future__ import annotations

import json
from importlib import resources

from researcher.domain.knowledge import Document, KnowledgeBase


class PackagedKnowledge:
    def __init__(
        self, package: str = "researcher.adapters.outbound", name: str = "data/knowledge.json"
    ) -> None:
        self._package = package
        self._name = name

    def load(self) -> KnowledgeBase:
        raw = resources.files(self._package).joinpath(self._name).read_text(encoding="utf-8")
        return KnowledgeBase([Document.from_dict(d) for d in json.loads(raw)["documents"]])
