"""Durable, non-authoritative telemetry for shadow resolver cycles."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def record_cycle(event: Dict[str, Any]) -> None:
    """Append one resolver-cycle event without affecting trading decisions."""
    try:
        from core.settings import RESOLVER_TELEMETRY_ENABLED, RESOLVER_TELEMETRY_LOG_PATH
        if not RESOLVER_TELEMETRY_ENABLED:
            return
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": "shadow_resolver",
            **dict(event or {}),
        }
        path = Path(RESOLVER_TELEMETRY_LOG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # Telemetry must never block or alter the trading loop.
        return