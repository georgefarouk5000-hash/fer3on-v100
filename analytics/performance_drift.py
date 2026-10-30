"""Shadow-only detector for context-specific performance deterioration."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def detect_performance_drift(
    records: Iterable[Dict[str, Any]],
    *,
    context_keys=("strategy", "regime", "session"),
    baseline_size: int = 30,
    recent_size: int = 10,
    min_samples: int = 10,
    win_rate_drop: float = 0.15,
) -> Dict[str, Any]:
    """Compare recent and baseline win rates by context; never advises trades."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records or []:
        key = "|".join(str(record.get(field, "UNKNOWN")).upper() for field in context_keys)
        outcome = str(record.get("result", record.get("outcome", ""))).upper()
        if outcome in {"WIN", "LOSS"}:
            grouped.setdefault(key, []).append(record)

    alerts = []
    contexts = {}
    for key, items in grouped.items():
        if len(items) < max(min_samples, recent_size):
            contexts[key] = {"samples": len(items), "status": "INSUFFICIENT_SAMPLE"}
            continue
        ordered = items[-max(baseline_size, recent_size):]
        baseline = ordered[:-recent_size] or ordered
        recent = ordered[-recent_size:]
        base_wr = sum(str(x.get("result", x.get("outcome"))).upper() == "WIN" for x in baseline) / len(baseline)
        recent_wr = sum(str(x.get("result", x.get("outcome"))).upper() == "WIN" for x in recent) / len(recent)
        drift = round(base_wr - recent_wr, 4)
        status = "DRIFT_ALERT" if len(baseline) >= min_samples and drift >= win_rate_drop else "STABLE"
        contexts[key] = {"samples": len(items), "baseline_wr": round(base_wr, 4), "recent_wr": round(recent_wr, 4), "drift": drift, "status": status}
        if status == "DRIFT_ALERT":
            alerts.append(key)
    return {"mode": "SHADOW", "contexts": contexts, "alerts": alerts, "alert_count": len(alerts)}