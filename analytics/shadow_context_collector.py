"""Append-only collection of regime and performance evidence for shadow review."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


DEFAULT_PATH = "data/analytics/shadow_context/context_observations.jsonl"


def _append(record: Dict[str, Any], path: Optional[str] = None) -> bool:
    try:
        target = path or DEFAULT_PATH
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "shadow_only": True, **record}
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def record_regime_observation(*, symbol: str, primary_regime: str,
                              recommended_strategy: str,
                              strategy_confidence: float,
                              observed_strategy: str, session: str,
                              path: Optional[str] = None) -> bool:
    return _append({
        "record_type": "REGIME_OBSERVATION",
        "symbol": symbol,
        "primary_regime": str(primary_regime or "UNKNOWN").upper(),
        "recommended_strategy": str(recommended_strategy or "UNKNOWN").upper(),
        "observed_strategy": str(observed_strategy or "UNKNOWN").upper(),
        "strategy_confidence": round(float(strategy_confidence or 0), 4),
        "session": str(session or "UNKNOWN").upper(),
    }, path)


def record_performance_snapshot(records: Iterable[Dict[str, Any]], *,
                               drift_result: Optional[Dict[str, Any]] = None,
                               path: Optional[str] = None) -> bool:
    items = list(records or [])
    wins = sum(str(item.get("result", item.get("outcome", ""))).upper() == "WIN" for item in items)
    losses = sum(str(item.get("result", item.get("outcome", ""))).upper() == "LOSS" for item in items)
    total = wins + losses
    return _append({
        "record_type": "PERFORMANCE_SNAPSHOT",
        "samples": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total, 4) if total else None,
        "drift_alert_count": int((drift_result or {}).get("alert_count", 0) or 0),
    }, path)