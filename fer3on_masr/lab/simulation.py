from __future__ import annotations

from typing import Any


class SimulationLab:
    def run(self, idea_name: str, sample_context: dict[str, Any]) -> dict[str, Any]:
        confidence = float(sample_context.get("base_confidence", 60.0))
        return {
            "idea": idea_name,
            "status": "simulated",
            "confidence": confidence,
            "result": "PASS" if confidence >= 55 else "REVIEW",
        }


class ReplaySystem:
    def replay(self, ticks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "tick_count": len(ticks),
            "first_tick": ticks[0] if ticks else None,
            "last_tick": ticks[-1] if ticks else None,
            "status": "replayed",
        }
