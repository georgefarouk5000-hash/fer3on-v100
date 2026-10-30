# =========================================
# FER3ON V5 — SELF OPTIMIZATION ENGINE
# =========================================

import json
import os
from datetime import datetime, timezone

from core.ai_memory import load_memory_records
from core.build_scope import filter_current_build_rows

OPTIMIZER_FILE = "data/analytics/self_optimizer.json"
CYCLE_SIZE = 50

DEFAULT_STATE = {
    "cycle": 0,
    "total_analyzed": 0,
    "last_run": None,
    "weights": {
        "SMC_threshold": 60,
        "DAILY_threshold": 58,
        "quality_soft_floor": 58,
        "quality_confidence_bypass": 80,
        "min_rr": 1.5,
        "smc_min_score": 3,
    },
    "performance_by_strategy": {},
    "performance_by_session": {},
    "performance_by_regime": {},
    "history": [],
}


def _load_state():
    if os.path.exists(OPTIMIZER_FILE):
        try:
            with open(OPTIMIZER_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            for k, v in DEFAULT_STATE.items():
                state.setdefault(k, v)
            for k, v in DEFAULT_STATE["weights"].items():
                state["weights"].setdefault(k, v)
            return state
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))


def _save_state(state):
    os.makedirs(os.path.dirname(OPTIMIZER_FILE), exist_ok=True)
    with open(OPTIMIZER_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _analyze_trades(n=50):
    # [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] المُحسِّن كان يعدّل العتبات من آخر
    # 50 صفقة مهما كانت نسختها. التحليل دلوقتي من صفقات البيلد الحالي فقط؛
    # ولو قلّت عن الحد الأدنى يرجع {} فيحافظ run_self_optimization على
    # الأوزان الافتراضية (fallback محافظ) بدل التعلّم من النسخة الفاشلة.
    rows = filter_current_build_rows(load_memory_records())
    if not rows:
        return {}
    recent = rows[-n:]
    stats = {"total": len(recent), "wins": 0, "losses": 0, "winrate": 0, "by_strategy": {}, "by_session": {}, "by_regime": {}, "avg_rr": 0}
    rr_values = []
    for row in recent:
        result = str(row.get("result", "")).upper()
        strat = row.get("strategy", "UNKNOWN")
        sess = row.get("session", "UNKNOWN")
        regime = row.get("market_regime", "UNKNOWN")

        if result == "WIN":
            stats["wins"] += 1
        elif result == "LOSS":
            stats["losses"] += 1

        for key, value in [("by_strategy", strat), ("by_session", sess), ("by_regime", regime)]:
            bucket = stats[key].setdefault(value, {"wins": 0, "losses": 0})
            if result == "WIN":
                bucket["wins"] += 1
            elif result == "LOSS":
                bucket["losses"] += 1

        try:
            rr = float(row.get("rr_ratio", 0) or 0)
            if rr > 0:
                rr_values.append(rr)
        except Exception:
            pass

    if stats["total"] > 0:
        stats["winrate"] = round(stats["wins"] / stats["total"] * 100, 1)
    if rr_values:
        stats["avg_rr"] = round(sum(rr_values) / len(rr_values), 2)
    return stats


def _adjust_weights(stats, current_weights):
    new_weights = current_weights.copy()
    changes = []
    for strat, data in stats.get("by_strategy", {}).items():
        total = data["wins"] + data["losses"]
        if total < 5:
            continue
        wr = data["wins"] / total
        key = f"{strat}_threshold"
        new_weights.setdefault(key, 60)
        old_val = new_weights[key]
        if wr < 0.40:
            new_weights[key] = min(old_val + 5, 90)
            changes.append(f"↑ {strat} threshold {old_val}→{new_weights[key]} (WR={wr:.0%})")
        elif wr > 0.65 and old_val > 58:
            new_weights[key] = max(old_val - 2, 58)
            changes.append(f"↓ {strat} threshold {old_val}→{new_weights[key]} (WR={wr:.0%})")

    avg_rr = stats.get("avg_rr", 0)
    if 0 < avg_rr < 1.5:
        old_rr = new_weights["min_rr"]
        new_weights["min_rr"] = min(old_rr + 0.1, 2.5)
        changes.append(f"↑ min_rr {old_rr}→{new_weights['min_rr']} (avg_rr={avg_rr})")
    elif avg_rr > 2.5 and new_weights["min_rr"] > 1.5:
        old_rr = new_weights["min_rr"]
        new_weights["min_rr"] = max(old_rr - 0.1, 1.5)
        changes.append(f"↓ min_rr {old_rr}→{new_weights['min_rr']} (avg_rr={avg_rr})")
    return new_weights, changes


def run_self_optimization(force=False):
    state = _load_state()
    # [BRAIN-SCOPE] عدّ الصفقات الجديدة على أساس صفقات البيلد الحالي فقط
    rows_count = len(filter_current_build_rows(load_memory_records()))
    new_trades = rows_count - state.get("total_analyzed", 0)
    if not force and new_trades < CYCLE_SIZE:
        return {"ran": False, "reason": f"Need {CYCLE_SIZE - new_trades} more trades"}

    stats = _analyze_trades(CYCLE_SIZE)
    if not stats or stats.get("total", 0) < 10:
        return {"ran": False, "reason": "INSUFFICIENT_DATA"}

    new_weights, changes = _adjust_weights(stats, state["weights"])
    state["cycle"] += 1
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["weights"] = new_weights
    state["total_analyzed"] = rows_count
    state["performance_by_strategy"] = stats.get("by_strategy", {})
    state["performance_by_session"] = stats.get("by_session", {})
    state["performance_by_regime"] = stats.get("by_regime", {})
    state["history"].append({"date": state["last_run"], "changes": changes, "stats": stats})
    state["history"] = state["history"][-20:]
    _save_state(state)
    return {"ran": True, "cycle": state["cycle"], "changes": changes, "weights": new_weights, "stats": stats}


def run_self_optimization_v51(force=False):
    return run_self_optimization(force=force)


def get_optimizer_weights():
    return _load_state().get("weights", DEFAULT_STATE["weights"])
