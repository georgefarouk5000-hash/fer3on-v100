"""Episodic market intelligence memory for FER3ON."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


class ContextualMemory:
    """Stores and recalls contextual market episodes with weighted similarity."""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        self.storage_path = storage_path or os.path.join("data", "memory", "contextual_memory.json")
        self.episodes: List[Dict[str, Any]] = []
        self._load()

    def remember_episode(
        self,
        regime: str,
        volatility: float,
        spread: float,
        liquidity_structure: str,
        session: str,
        recovery_state: str,
        execution_quality: float,
        outcome: str,
        setup_type: str,
        strategy: str = "UNKNOWN",
        notes: str = "",
    ) -> Dict[str, Any]:
        episode = {
            "regime": (regime or "UNKNOWN").upper(),
            "volatility": round(float(volatility), 3),
            "spread": round(float(spread), 3),
            "liquidity_structure": (liquidity_structure or "UNKNOWN").upper(),
            "session": (session or "UNKNOWN").upper(),
            "recovery_state": (recovery_state or "NONE").upper(),
            "execution_quality": round(float(execution_quality), 3),
            "outcome": (outcome or "UNKNOWN").upper(),
            "setup_type": (setup_type or "UNKNOWN").upper(),
            "strategy": (strategy or "UNKNOWN").upper(),
            "notes": notes,
        }
        self.episodes.append(episode)
        self._save()
        return episode

    def weighted_recall(
        self,
        regime: str,
        volatility: float,
        spread: float,
        liquidity_structure: str,
        session: str,
        recovery_state: str,
        execution_quality: float,
        setup_type: str = "UNKNOWN",
        strategy: str = "UNKNOWN",
    ) -> Dict[str, Any]:
        if not self.episodes:
            return {"score": 0.0, "matched_episodes": []}

        query = {
            "regime": (regime or "UNKNOWN").upper(),
            "volatility": round(float(volatility), 3),
            "spread": round(float(spread), 3),
            "liquidity_structure": (liquidity_structure or "UNKNOWN").upper(),
            "session": (session or "UNKNOWN").upper(),
            "recovery_state": (recovery_state or "NONE").upper(),
            "execution_quality": round(float(execution_quality), 3),
            "setup_type": (setup_type or "UNKNOWN").upper(),
            "strategy": (strategy or "UNKNOWN").upper(),
        }

        scored = []
        for episode in self.episodes:
            score = 0.0
            if episode.get("regime") == query["regime"]:
                score += 0.25
            if abs(float(episode.get("volatility", 0)) - query["volatility"]) < 0.4:
                score += 0.20
            if abs(float(episode.get("spread", 0)) - query["spread"]) < 1.0:
                score += 0.20
            if episode.get("liquidity_structure") == query["liquidity_structure"]:
                score += 0.15
            if episode.get("session") == query["session"]:
                score += 0.10
            if episode.get("setup_type") == query["setup_type"]:
                score += 0.10
            if episode.get("strategy") == query["strategy"]:
                score += 0.10
            if episode.get("recovery_state") == query["recovery_state"]:
                score += 0.05
            if episode.get("execution_quality", 0.0) >= query["execution_quality"] - 0.2:
                score += 0.05
            if episode.get("outcome") == "WIN":
                score += 0.10
            scored.append((score, episode))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:3]
        best_score = round(top[0][0] if top else 0.0, 3)
        return {
            "score": best_score,
            "matched_episodes": [episode for _, episode in top],
        }

    def _load(self) -> None:
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                    self.episodes = raw if isinstance(raw, list) else []
        except Exception:
            self.episodes = []

    def _save(self) -> None:
        try:
            directory = os.path.dirname(self.storage_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as handle:
                json.dump(self.episodes, handle, indent=2)
        except Exception:
            pass
