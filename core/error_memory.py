"""Append-only memory for trade and decision failure patterns."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


DEFAULT_PATH = "data/memory/error_memory.jsonl"


def record_error_episode(
    *,
    category: str,
    outcome: str,
    strategy: Optional[str] = None,
    regime: Optional[str] = None,
    session: Optional[str] = None,
    confidence: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
) -> bool:
    """Record an error episode without influencing the trading decision."""
    try:
        target = path or DEFAULT_PATH
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": str(category or "UNKNOWN").upper(),
            "outcome": str(outcome or "UNKNOWN").upper(),
            "strategy": str(strategy or "UNKNOWN").upper(),
            "regime": str(regime or "UNKNOWN").upper(),
            "session": str(session or "UNKNOWN").upper(),
            "confidence": None if confidence is None else round(float(confidence), 3),
            "details": dict(details or {}),
            "shadow_only": True,
        }
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False