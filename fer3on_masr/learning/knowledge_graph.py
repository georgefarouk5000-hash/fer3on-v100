from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class KnowledgeEdge:
    source: str
    relation: str
    target: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "weight": self.weight,
            "metadata": self.metadata,
        }


class KnowledgeGraph:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.nodes: set[str] = set()
        self.edges: list[KnowledgeEdge] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.load()

    def add_relation(self, source: str, relation: str, target: str, weight: float = 1.0, **metadata: Any) -> None:
        self.nodes.add(source)
        self.nodes.add(target)
        self.edges.append(KnowledgeEdge(source, relation, target, weight, metadata))

    def seed_default_relations(self) -> None:
        defaults = [
            ("Liquidity Sweep", "linked_to", "Bearish", 0.82),
            ("Bearish", "appears_in", "London", 0.74),
            ("London", "expands", "ATR Expansion", 0.79),
            ("ATR Expansion", "improves", "Breakout Success", 0.81),
            ("High ATR + Sweep + Pin Bar", "discovers", "Pattern Discovery", 0.91),
        ]
        if self.edges:
            return
        for source, relation, target, weight in defaults:
            self.add_relation(source, relation, target, weight)

    def query(self, term: str) -> list[dict[str, Any]]:
        term = term.lower().strip()
        results = []
        for edge in self.edges:
            haystack = f"{edge.source} {edge.relation} {edge.target}".lower()
            if term in haystack:
                results.append(edge.to_dict())
        return results

    def save(self) -> None:
        payload = {
            "nodes": sorted(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.nodes = set(data.get("nodes", []))
        self.edges = [KnowledgeEdge(**edge) for edge in data.get("edges", [])]
