# =========================================
# FER3ON V6 Recovery+ — ADAPTIVE FILTER RELAXATION
# Reduces filter strictness based on false rejection stats
# Maximum relaxation: 20% — never fully disables filters
# =========================================

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    V7_PLUS_ENABLED,
    V7_FILTER_RELAXATION_ENABLED,
    V7_FILTER_RELAXATION_MAX,
    ANALYTICS_DIR,
)

STORE_FILE = os.path.join(ANALYTICS_DIR, "filter_relaxation.json")

_DEFAULT_STORE: Dict[str, Any] = {"filter_stats": {}, "history": []}

DEFAULT_FILTER_WEIGHTS = {
    "quality_gate": 1.0,
    "daily_bias": 1.0,
    "mtf_required": 1.0,
    "rsi_filter": 1.0,
    "structure_conflict": 1.0,
    "liquidity_conflict": 1.0,
    "ml_gate": 1.0,
    "exec_intelligence": 1.0,
}

FALSE_REJECTION_RELAX_THRESHOLD = 0.30


def _ensure_store() -> None:
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    if not os.path.exists(STORE_FILE):
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_STORE, f, indent=4)


def _load_store() -> Dict[str, Any]:
    _ensure_store()
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("corrupted store: root is not an object")
        return data
    except Exception:
        rebuilt = dict(_DEFAULT_STORE)
        _save_store(rebuilt)
        return rebuilt


def _save_store(data: Dict[str, Any]) -> None:
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_filter_relaxation_factor(
    false_rejection_rate: float,
    missed_opportunity_score: float = 50.0,
) -> float:
    """
    FILTER_RELAXATION_FACTOR 0–1.
    1.0 = no relaxation (default).
    0.0 = maximum relaxation (20% threshold reduction).
    """
    if not V7_PLUS_ENABLED or not V7_FILTER_RELAXATION_ENABLED:
        return 1.0

    rate = _clamp(float(false_rejection_rate or 0) / 100.0, 0.0, 1.0)
    missed = _clamp(float(missed_opportunity_score or 50) / 100.0, 0.0, 1.0)

    if rate < FALSE_REJECTION_RELAX_THRESHOLD:
        return 1.0

    excess = (rate - FALSE_REJECTION_RELAX_THRESHOLD) / max(1.0 - FALSE_REJECTION_RELAX_THRESHOLD, 0.01)
    missed_pressure = 1.0 - missed
    raw_relax = excess * 0.6 + missed_pressure * 0.4

    max_relax = float(V7_FILTER_RELAXATION_MAX)
    relaxation_amount = _clamp(raw_relax * max_relax, 0.0, max_relax)
    factor = round(1.0 - relaxation_amount, 4)
    return _clamp(factor, 1.0 - max_relax, 1.0)


def compute_per_filter_weights(
    filter_stats: Dict[str, Dict[str, int]],
    base_factor: float,
) -> Dict[str, float]:
    """
    Adjust individual filter weights based on per-filter false rejection counts.
    Never below (1 - MAX_RELAXATION).
    """
    max_relax = float(V7_FILTER_RELAXATION_MAX)
    floor = 1.0 - max_relax
    weights = dict(DEFAULT_FILTER_WEIGHTS)

    if not filter_stats:
        relax_pct = (1.0 - base_factor) / max_relax if max_relax > 0 else 0.0
        for key in weights:
            weights[key] = round(_clamp(1.0 - relax_pct * max_relax, floor, 1.0), 4)
        return weights

    for filter_name, stats in filter_stats.items():
        total = int(stats.get("total", 0) or 0)
        false_r = int(stats.get("false_rejections", 0) or 0)
        if total < 3:
            continue
        false_rate = false_r / total
        if false_rate >= FALSE_REJECTION_RELAX_THRESHOLD:
            excess = (false_rate - FALSE_REJECTION_RELAX_THRESHOLD) / (
                1.0 - FALSE_REJECTION_RELAX_THRESHOLD
            )
            relax = min(max_relax, excess * max_relax * base_factor)
            canon = filter_name if filter_name in weights else "quality_gate"
            weights[canon] = round(_clamp(1.0 - relax, floor, 1.0), 4)

    return weights


def apply_threshold_relaxation(
    threshold: float,
    relaxation_factor: float,
) -> float:
    """Apply relaxation to a numeric threshold (lowers strictness)."""
    threshold = float(threshold or 0)
    if threshold <= 0:
        return threshold
    max_relax = float(V7_FILTER_RELAXATION_MAX)
    relax_pct = (1.0 - float(relaxation_factor)) / max_relax * max_relax if max_relax > 0 else 0.0
    relax_pct = _clamp(relax_pct, 0.0, max_relax)
    relaxed = threshold * (1.0 - relax_pct)
    return round(max(0.0, relaxed), 2)


def record_filter_rejection(
    rejection_reason: str,
    strategy: str = "UNKNOWN",
    session: str = "UNKNOWN",
    regime: str = "UNKNOWN",
) -> None:
    """Track rejection counts per filter for adaptive relaxation."""
    if not V7_PLUS_ENABLED or not V7_FILTER_RELAXATION_ENABLED:
        return

    reason = str(rejection_reason or "UNKNOWN").upper()
    data = _load_store()
    stats = data.setdefault("filter_stats", {})
    key = reason

    if key not in stats:
        stats[key] = {"total": 0, "false_rejections": 0, "strategy": strategy, "session": session}

    stats[key]["total"] = int(stats[key].get("total", 0)) + 1
    _save_store(data)


def record_filter_false_rejection(rejection_reason: str) -> None:
    """Increment false rejection count for a filter reason."""
    if not V7_PLUS_ENABLED or not V7_FILTER_RELAXATION_ENABLED:
        return

    reason = str(rejection_reason or "UNKNOWN").upper()
    data = _load_store()
    stats = data.setdefault("filter_stats", {})

    if reason not in stats:
        stats[reason] = {"total": 0, "false_rejections": 0}

    stats[reason]["false_rejections"] = int(stats[reason].get("false_rejections", 0)) + 1
    _save_store(data)


def sync_false_rejections_from_missed_opportunity(
    evaluated_records: List[Dict[str, Any]],
) -> None:
    """Sync filter stats from missed opportunity evaluated records."""
    if not evaluated_records:
        return

    for rec in evaluated_records:
        if rec.get("outcome") != "FALSE_REJECTION":
            continue
        reason = str(rec.get("rejection_reason", "FINAL_BRAIN") or "FINAL_BRAIN").upper()
        record_filter_rejection(reason)
        record_filter_false_rejection(reason)


def analyze_filter_relaxation(
    false_rejection_rate: float = 0.0,
    missed_opportunity_score: float = 50.0,
    strategy: Optional[str] = None,
    session: Optional[str] = None,
    regime: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full filter relaxation analysis.
    Returns FILTER_RELAXATION_FACTOR and per-filter weights.
    """
    if not V7_PLUS_ENABLED or not V7_FILTER_RELAXATION_ENABLED:
        return {
            "enabled": False,
            "filter_relaxation_factor": 1.0,
            "filter_weights": dict(DEFAULT_FILTER_WEIGHTS),
            "relaxation_pct": 0.0,
            "reason": "DISABLED",
        }

    if rejection_reason:
        record_filter_rejection(
            rejection_reason,
            strategy=strategy or "UNKNOWN",
            session=session or "UNKNOWN",
            regime=regime or "UNKNOWN",
        )

    data = _load_store()
    factor = compute_filter_relaxation_factor(false_rejection_rate, missed_opportunity_score)
    weights = compute_per_filter_weights(data.get("filter_stats", {}), factor)
    max_relax = float(V7_FILTER_RELAXATION_MAX)
    relaxation_pct = round((1.0 - factor) / max_relax * 100, 2) if max_relax > 0 else 0.0

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "factor": factor,
        "false_rejection_rate": false_rejection_rate,
        "missed_opportunity_score": missed_opportunity_score,
        "strategy": strategy,
        "session": session,
        "regime": regime,
    }
    history = data.setdefault("history", [])
    history.append(entry)
    if len(history) > 500:
        history[:] = history[-500:]
    _save_store(data)

    print(
        f"[RECOVERY+] FILTER_RELAXATION: factor={factor}"
        f" | relax={relaxation_pct:.1f}%"
        f" | false_rate={false_rejection_rate}%"
        f" | missed_score={missed_opportunity_score}"
    )

    return {
        "enabled": True,
        "filter_relaxation_factor": factor,
        "filter_weights": weights,
        "relaxation_pct": round((1.0 - factor) * 100, 2),
        "reason": "ACTIVE",
    }
