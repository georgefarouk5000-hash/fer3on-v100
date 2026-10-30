# =============================================================================
# FER3ON V7.0 — ADAPTIVE LEARNING ENGINE
# =============================================================================
# البوت يتعلم من الصفقات تلقائياً:
#   - يراقب WR / Expectancy / Drawdown
#   - يعدّل thresholds (يخفف لو الأداء كويس، يشدد لو خسارة متتالية)
#   - يحفظ snapshots في data/analytics/adaptive_state.json
#   - يقترح best_strategy حسب الجلسة والـ regime
# =============================================================================

import json
import os
import time
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional

from core.settings import (
    ADAPTIVE_LEARNING_ENABLED,
    ADAPTIVE_MIN_TRADES_TO_TUNE,
    ADAPTIVE_TUNE_INTERVAL,
    ADAPTIVE_THRESHOLD_STEP,
    ADAPTIVE_MAX_TIGHTEN,
    ADAPTIVE_MAX_RELAX,
    ADAPTIVE_WR_GOOD_LIFT,
    ADAPTIVE_WR_BAD_TIGHTEN,
    ANALYTICS_DIR,
    COMPOSITE_FULL_MIN,
    COMPOSITE_REDUCED_MIN,
    COMPOSITE_MICRO_MIN,
)


STATE_FILE = os.path.join(ANALYTICS_DIR, "adaptive_state.json")
TRADE_LOG_FILE = os.path.join(ANALYTICS_DIR, "adaptive_trades.jsonl")


# =============================================================================
# STATE PERSISTENCE
# =============================================================================

DEFAULT_STATE: Dict[str, Any] = {
    "version": "7.0",
    "total_trades": 0,
    "wins": 0,
    "losses": 0,
    "last_tune_at_trade": 0,
    # threshold offsets — added to base thresholds at decision time
    "offsets": {
        "composite_full":    0,
        "composite_reduced": 0,
        "composite_micro":   0,
    },
    # rolling window (last 30 trades)
    "recent_results": [],   # list of {strategy, session, regime, pnl, win}
    # per-context performance
    "per_strategy": {},
    "per_session":  {},
    "per_regime":   {},
    "updated_at": 0,
    "tune_log": [],
}


def _ensure_dirs():
    os.makedirs(ANALYTICS_DIR, exist_ok=True)


def load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(STATE_FILE):
        return dict(DEFAULT_STATE)
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # safety: merge keys
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULT_STATE)


def save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    state["updated_at"] = int(time.time())
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# =============================================================================
# TRADE RECORDING
# =============================================================================

def record_trade_outcome(
    strategy: str,
    session: str,
    regime: str,
    signal: str,
    composite_score: float,
    size_mode: str,
    pnl: float,
    win: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    يستدعى بعد إغلاق كل صفقة.
    win = True / False / None (لو None — يحسب من pnl)
    """
    if not ADAPTIVE_LEARNING_ENABLED:
        return {"skipped": True}

    if win is None:
        win = bool(pnl > 0)

    state = load_state()
    state["total_trades"] = int(state.get("total_trades", 0)) + 1
    if win:
        state["wins"] = int(state.get("wins", 0)) + 1
    else:
        state["losses"] = int(state.get("losses", 0)) + 1

    rec = {
        "ts": int(time.time()),
        "strategy": strategy,
        "session": session,
        "regime": regime,
        "signal": signal,
        "composite": round(float(composite_score or 0), 2),
        "size_mode": size_mode,
        "pnl": round(float(pnl or 0), 4),
        "win": bool(win),
    }
    # rolling 30
    recent = list(state.get("recent_results", []))
    recent.append(rec)
    if len(recent) > 30:
        recent = recent[-30:]
    state["recent_results"] = recent

    # per-context aggregates
    for key, val in (("per_strategy", strategy), ("per_session", session), ("per_regime", regime)):
        bucket = dict(state.get(key, {}))
        b = dict(bucket.get(val, {"trades": 0, "wins": 0, "pnl": 0.0}))
        b["trades"] = int(b.get("trades", 0)) + 1
        if win:
            b["wins"] = int(b.get("wins", 0)) + 1
        b["pnl"] = round(float(b.get("pnl", 0.0)) + float(pnl or 0), 4)
        bucket[val] = b
        state[key] = bucket

    # append jsonl
    _ensure_dirs()
    try:
        with open(TRADE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # auto-tune trigger
    since_last = state["total_trades"] - int(state.get("last_tune_at_trade", 0))
    if (
        state["total_trades"] >= ADAPTIVE_MIN_TRADES_TO_TUNE
        and since_last >= ADAPTIVE_TUNE_INTERVAL
    ):
        tune_thresholds(state)

    save_state(state)
    return rec


# =============================================================================
# AUTO-TUNING LOGIC
# =============================================================================

def _calc_recent_wr(state: Dict[str, Any]) -> float:
    recent = state.get("recent_results", [])
    if not recent:
        return 0.5
    wins = sum(1 for r in recent if r.get("win"))
    return wins / max(1, len(recent))


def _calc_recent_expectancy(state: Dict[str, Any]) -> float:
    recent = state.get("recent_results", [])
    if not recent:
        return 0.0
    total = sum(float(r.get("pnl", 0) or 0) for r in recent)
    return total / max(1, len(recent))


def tune_thresholds(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    يعدّل offsets بناءً على آخر 30 صفقة.
    WR ≥ 62%  → يخفف (-step) — يسمح بمرور أكتر
    WR ≤ 42%  → يشدد (+step) — يصد borderline
    بينهم → لا تغيير
    """
    wr = _calc_recent_wr(state)
    exp = _calc_recent_expectancy(state)
    offsets = dict(state.get("offsets", {}))

    direction = 0
    if wr >= ADAPTIVE_WR_GOOD_LIFT and exp >= 0:
        direction = -1   # relax (lower threshold)
    elif wr <= ADAPTIVE_WR_BAD_TIGHTEN or exp < 0:
        direction = +1   # tighten

    step = ADAPTIVE_THRESHOLD_STEP * direction

    for key in ("composite_full", "composite_reduced", "composite_micro"):
        cur = float(offsets.get(key, 0))
        new = cur + step
        new = max(-ADAPTIVE_MAX_RELAX, min(ADAPTIVE_MAX_TIGHTEN, new))
        offsets[key] = round(new, 2)

    state["offsets"] = offsets
    state["last_tune_at_trade"] = int(state.get("total_trades", 0))

    tune_log = list(state.get("tune_log", []))
    tune_log.append({
        "ts": int(time.time()),
        "wr": round(wr, 3),
        "expectancy": round(exp, 4),
        "direction": direction,
        "offsets": offsets,
    })
    if len(tune_log) > 50:
        tune_log = tune_log[-50:]
    state["tune_log"] = tune_log
    return state


def get_adjusted_thresholds() -> Dict[str, float]:
    """يرجع الـ thresholds بعد تطبيق offsets الـ adaptive."""
    state = load_state()
    off = state.get("offsets", {})
    return {
        "full":    COMPOSITE_FULL_MIN    + float(off.get("composite_full", 0)),
        "reduced": COMPOSITE_REDUCED_MIN + float(off.get("composite_reduced", 0)),
        "micro":   COMPOSITE_MICRO_MIN   + float(off.get("composite_micro", 0)),
    }


# =============================================================================
# CONTEXT INTELLIGENCE — قبل القرار
# =============================================================================

def get_recent_wr(window: int = 30) -> float:
    state = load_state()
    recent = state.get("recent_results", [])[-window:]
    if not recent:
        return 0.5
    wins = sum(1 for r in recent if r.get("win"))
    return wins / max(1, len(recent))


def get_recent_losses(window: int = 5) -> int:
    state = load_state()
    recent = state.get("recent_results", [])[-window:]
    streak = 0
    for r in reversed(recent):
        if not r.get("win"):
            streak += 1
        else:
            break
    return streak


def best_strategy_for_context(session: str, regime: str) -> Optional[str]:
    """
    يقترح أفضل استراتيجية بناءً على الأداء السابق في نفس السياق.
    يرجع None لو لا يوجد بيانات كافية → النظام يستخدم اختياره الافتراضي.
    """
    state = load_state()
    recent = state.get("recent_results", [])
    if len(recent) < 8:
        return None

    scores: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for r in recent:
        if r.get("session") != session and session != "ANY":
            continue
        strat = str(r.get("strategy") or "").upper()
        if strat not in {"SMC", "DAILY"}:
            continue
        counts[strat] += 1
        # expectancy contribution
        pnl = float(r.get("pnl", 0) or 0)
        scores[strat] += pnl + (3 if r.get("win") else -2)

    if not scores:
        return None

    # require ≥2 trades for a strategy to be eligible
    eligible = {k: v for k, v in scores.items() if counts[k] >= 2}
    if not eligible:
        return None

    best = max(eligible.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else None


# =============================================================================
# PUBLIC SUMMARY (for /tune telegram command)
# =============================================================================

def get_status_summary() -> Dict[str, Any]:
    state = load_state()
    wr = _calc_recent_wr(state)
    exp = _calc_recent_expectancy(state)
    th = get_adjusted_thresholds()
    return {
        "enabled": ADAPTIVE_LEARNING_ENABLED,
        "total_trades": state.get("total_trades", 0),
        "wins": state.get("wins", 0),
        "losses": state.get("losses", 0),
        "recent_wr": round(wr, 3),
        "recent_expectancy": round(exp, 4),
        "thresholds": th,
        "offsets": state.get("offsets", {}),
        "last_tune_at_trade": state.get("last_tune_at_trade", 0),
        "per_strategy": state.get("per_strategy", {}),
        "per_session": state.get("per_session", {}),
        "per_regime": state.get("per_regime", {}),
    }


def format_status_text() -> str:
    s = get_status_summary()
    lines = [
        f"🧠 ADAPTIVE LEARNING — {'ON' if s['enabled'] else 'OFF'}",
        f"Trades: {s['total_trades']} (W:{s['wins']} L:{s['losses']})",
        f"Recent WR: {s['recent_wr']*100:.1f}%  | Exp: {s['recent_expectancy']:+.4f}",
        f"Thresholds — Full:{s['thresholds']['full']:.1f}  Red:{s['thresholds']['reduced']:.1f}  Micro:{s['thresholds']['micro']:.1f}",
        f"Offsets: {s['offsets']}",
    ]
    return "\n".join(lines)
