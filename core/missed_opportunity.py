# =========================================
# FER3ON V7 — MISSED OPPORTUNITY TRACKER
# Tracks rejected setups and evaluates follow-through
# =========================================

import copy
import json
import os
import time
import uuid
from datetime import datetime, timezone

from core.settings import (
    V7_MISSED_OPPORTUNITY_ENABLED,
    V7_MISSED_EVAL_MINUTES,
    V7_MOVEMENT_THRESHOLDS,
    ANALYTICS_DIR,
)

STORE_FILE = os.path.join(ANALYTICS_DIR, "missed_opportunities.json")
EVAL_SECONDS = V7_MISSED_EVAL_MINUTES * 60
_STORE_CACHE = None


def _reset_store_state():
    global _STORE_CACHE
    _STORE_CACHE = {"pending": [], "evaluated": [], "stats": _empty_stats()}


def _ensure_store():
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    if not os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE, "w", encoding="utf-8") as f:
                json.dump({"pending": [], "evaluated": [], "stats": _empty_stats()}, f)
        except (PermissionError, OSError):
            return False
    return True


def _empty_stats():
    return {
        "total_rejections": 0,
        "false_rejections": 0,
        "false_rejection_rate": 0.0,
        "missed_opportunity_score": 50.0,
    }


def _load():
    global _STORE_CACHE
    if _STORE_CACHE is not None:
        return copy.deepcopy(_STORE_CACHE)

    _ensure_store()
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (PermissionError, OSError, json.JSONDecodeError):
        data = {"pending": [], "evaluated": [], "stats": _empty_stats()}
    data.setdefault("pending", [])
    data.setdefault("evaluated", [])
    data.setdefault("stats", _empty_stats())
    _STORE_CACHE = copy.deepcopy(data)
    return copy.deepcopy(data)


def _save(data):
    global _STORE_CACHE
    _STORE_CACHE = copy.deepcopy(data)
    _ensure_store()
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except (PermissionError, OSError):
        return False
    return True


def compute_missed_opportunity_score(stats):
    """
    MISSED_OPPORTUNITY_SCORE 0–100.
    Higher = fewer false rejections (better filter calibration).
    """
    total = int(stats.get("total_rejections", 0) or 0)
    false_r = int(stats.get("false_rejections", 0) or 0)
    if total <= 0:
        return 50.0
    false_rate = false_r / total
    score = round(max(0.0, min(100.0, 100.0 - false_rate * 100.0)), 2)
    return score


def _update_stats(data):
    evaluated = data.get("evaluated", [])
    total = len(evaluated)
    false_r = sum(1 for e in evaluated if e.get("outcome") == "FALSE_REJECTION")
    rate = round(false_r / total * 100, 2) if total else 0.0
    data["stats"] = {
        "total_rejections": total,
        "false_rejections": false_r,
        "false_rejection_rate": rate,
        "missed_opportunity_score": compute_missed_opportunity_score(
            {"total_rejections": total, "false_rejections": false_r}
        ),
    }
    return data["stats"]


def record_rejection(
    symbol,
    strategy,
    direction,
    confidence,
    setup_score,
    regime,
    session,
    liquidity_bias,
    structure_bias,
    entry_price=0.0,
    verdict="REJECT",
    rejection_reason="FINAL_BRAIN",
    entry_timing="UNKNOWN",
    sl_diagnostic="UNKNOWN",
):
    """Store a rejected/WAIT setup for later evaluation."""
    if not V7_MISSED_OPPORTUNITY_ENABLED:
        return None

    record = {
        "id": str(uuid.uuid4())[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eval_after": time.time() + EVAL_SECONDS,
        "symbol": symbol,
        "strategy": strategy,
        "direction": direction,
        "confidence": round(float(confidence or 0), 2),
        "setup_score": round(float(setup_score or 0), 2),
        "regime": regime,
        "session": session,
        "liquidity_bias": liquidity_bias,
        "structure_bias": structure_bias,
        "entry_price": round(float(entry_price or 0), 2),
        "verdict": verdict,
        "rejection_reason": str(rejection_reason or "FINAL_BRAIN").upper(),
        "entry_timing": str(entry_timing or "UNKNOWN").upper(),
        "sl_diagnostic": str(sl_diagnostic or "UNKNOWN").upper(),
        "evaluated": False,
    }

    data = _load()
    data["pending"].append(record)
    _save(data)

    print(
        f"[FER3ON AI V2] MISSED_OPP RECORDED | {strategy} {direction}"
        f" | conf={record['confidence']}"
        f" | setup={record['setup_score']}"
        f" | eval_in={V7_MISSED_EVAL_MINUTES}m"
    )
    return record["id"]


def _directional_move(entry_price, current_price, direction):
    """Points moved in signal direction (gold price units)."""
    if entry_price <= 0 or current_price <= 0:
        return 0.0
    if direction == "BUY":
        return max(0.0, current_price - entry_price)
    if direction == "SELL":
        return max(0.0, entry_price - current_price)
    return 0.0


def evaluate_movement_thresholds(move_points, thresholds=None):
    """Return dict of threshold -> hit (bool)."""
    thresholds = thresholds or V7_MOVEMENT_THRESHOLDS
    return {int(t): move_points >= float(t) for t in thresholds}


def classify_rejection_outcome(move_points, min_threshold=10):
    """FALSE_REJECTION if price moved favorably past min threshold."""
    if move_points >= float(min_threshold):
        return "FALSE_REJECTION"
    return "VALID_REJECTION"


def evaluate_pending(symbol, get_price_fn):
    """
    Evaluate pending rejections older than eval window.
    get_price_fn(symbol) -> current mid price.
    """
    if not V7_MISSED_OPPORTUNITY_ENABLED:
        return {"evaluated": 0, "stats": _empty_stats()}

    data = _load()
    now = time.time()
    still_pending = []
    evaluated_count = 0

    for rec in data.get("pending", []):
        if rec.get("symbol") != symbol:
            still_pending.append(rec)
            continue
        if now < rec.get("eval_after", 0):
            still_pending.append(rec)
            continue

        entry = float(rec.get("entry_price", 0) or 0)
        current = float(get_price_fn(symbol) or 0)
        move = _directional_move(entry, current, rec.get("direction", "NONE"))
        thresholds_hit = evaluate_movement_thresholds(move)
        outcome = classify_rejection_outcome(move)

        rec["evaluated"] = True
        rec["eval_time"] = datetime.now(timezone.utc).isoformat()
        rec["price_at_eval"] = round(current, 2)
        rec["move_points"] = round(move, 2)
        rec["thresholds_hit"] = thresholds_hit
        rec["outcome"] = outcome
        data["evaluated"].append(rec)
        evaluated_count += 1

        print(
            f"[FER3ON AI V2] MISSED_OPP EVAL | {rec['strategy']} {rec['direction']}"
            f" | move={move:.1f}pts"
            f" | outcome={outcome}"
            f" | hits={thresholds_hit}"
        )

    data["pending"] = still_pending
    stats = _update_stats(data)
    _save(data)

    return {"evaluated": evaluated_count, "stats": stats}


def get_missed_opportunity_stats():
    data = _load()
    return data.get("stats", _empty_stats())


def get_evaluated_records():
    """Return all evaluated missed-opportunity records."""
    data = _load()
    return list(data.get("evaluated", []))


def get_missed_opportunity_score():
    return get_missed_opportunity_stats().get("missed_opportunity_score", 50.0)
