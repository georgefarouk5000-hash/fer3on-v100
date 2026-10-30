# =========================================
# FER3ON V6 RECOVERY — CANDLE CONTEXT ENGINE
# Multi-candle context (5/10/20) — not single-candle only
# =========================================

from core.settings import V7_CANDLE_CONTEXT_ENABLED, V7_CANDLE_CONTEXT_MAX_BONUS
from core.micro_trigger import candle_value, _no_candles


def _closes(candles, n=None):
    if _no_candles(candles):
        return []
    window = candles[-n:] if n else list(candles)
    return [float(candle_value(c, "close", 0)) for c in window]


def _ranges(candles, n=None):
    if _no_candles(candles):
        return []
    window = candles[-n:] if n else list(candles)
    out = []
    for c in window:
        out.append(float(candle_value(c, "high", 0)) - float(candle_value(c, "low", 0)))
    return out


def _bodies(candles, n=None):
    if _no_candles(candles):
        return []
    window = candles[-n:] if n else list(candles)
    return [
        float(candle_value(c, "close", 0)) - float(candle_value(c, "open", 0))
        for c in window
    ]


def score_momentum_buildup(candles, signal, lookback=10):
    """Directional body expansion over recent window."""
    bodies = _bodies(candles, lookback)
    if len(bodies) < 4:
        return 0.0
    if signal == "BUY":
        aligned = sum(1 for b in bodies if b > 0)
        expansion = bodies[-1] > bodies[0] and bodies[-1] > 0
    elif signal == "SELL":
        aligned = sum(1 for b in bodies if b < 0)
        expansion = bodies[-1] < bodies[0] and bodies[-1] < 0
    else:
        return 0.0
    ratio = aligned / len(bodies)
    score = ratio * 15
    if expansion:
        score += 10
    return min(25.0, score)


def score_repeated_rejection(candles, signal, lookback=10):
    """Multiple wick rejections at same zone."""
    if _no_candles(candles) or len(candles) < 3:
        return 0.0
    window = candles[-lookback:]
    rejections = 0
    for c in window:
        rng = float(candle_value(c, "high", 0)) - float(candle_value(c, "low", 0))
        if rng <= 0:
            continue
        close = float(candle_value(c, "close", 0))
        open_ = float(candle_value(c, "open", 0))
        high = float(candle_value(c, "high", 0))
        low = float(candle_value(c, "low", 0))
        upper = high - max(open_, close)
        lower = min(open_, close) - low
        if signal == "BUY" and lower / rng >= 0.45:
            rejections += 1
        elif signal == "SELL" and upper / rng >= 0.45:
            rejections += 1
    return min(20.0, rejections * 5)


def score_absorption(candles, signal, lookback=10):
    """Small bodies after large range — absorption."""
    ranges = _ranges(candles, lookback)
    bodies = [abs(b) for b in _bodies(candles, lookback)]
    if len(ranges) < 4 or len(bodies) < 4:
        return 0.0
    avg_range = sum(ranges[:-2]) / max(len(ranges[:-2]), 1)
    recent_body = bodies[-1]
    prior_big = max(ranges[-4:-1]) > avg_range * 1.2
    if prior_big and recent_body < avg_range * 0.35:
        return 15.0
    return 0.0


def score_break_attempts(candles, signal, lookback=20):
    """Repeated highs/lows testing structure."""
    if _no_candles(candles) or len(candles) < 5:
        return 0.0
    window = candles[-lookback:]
    highs = [float(candle_value(c, "high", 0)) for c in window]
    lows = [float(candle_value(c, "low", 0)) for c in window]
    if signal == "BUY":
        swing = max(highs[:-1]) if len(highs) > 1 else highs[-1]
        touches = sum(1 for h in highs[-5:] if abs(h - swing) < (swing * 0.0003 + 0.5))
        if highs[-1] > swing:
            return min(20.0, 10 + touches * 3)
        return min(12.0, touches * 4)
    if signal == "SELL":
        swing = min(lows[:-1]) if len(lows) > 1 else lows[-1]
        touches = sum(1 for l in lows[-5:] if abs(l - swing) < (abs(swing) * 0.0003 + 0.5))
        if lows[-1] < swing:
            return min(20.0, 10 + touches * 3)
        return min(12.0, touches * 4)
    return 0.0


def compute_candle_context_score(candles, signal):
    """CANDLE_CONTEXT_SCORE 0–100 from multi-window analysis."""
    s5 = (
        score_momentum_buildup(candles, signal, 5) * 0.4
        + score_repeated_rejection(candles, signal, 5) * 0.3
        + score_break_attempts(candles, signal, 5) * 0.3
    )
    s10 = (
        score_momentum_buildup(candles, signal, 10) * 0.35
        + score_repeated_rejection(candles, signal, 10) * 0.35
        + score_absorption(candles, signal, 10) * 0.30
    )
    s20 = (
        score_momentum_buildup(candles, signal, 20) * 0.30
        + score_absorption(candles, signal, 20) * 0.30
        + score_break_attempts(candles, signal, 20) * 0.40
    )
    raw = s5 * 0.35 + s10 * 0.40 + s20 * 0.25
    return round(min(100.0, raw * 2.0), 2)


def analyze_candle_context(candles, signal):
    """
    Full candle context analysis.
    Used alongside (not instead of) single-candle trigger.
    """
    if not V7_CANDLE_CONTEXT_ENABLED:
        return {
            "candle_context_score": 0.0,
            "confidence_bonus": 0.0,
            "weight_bonus": 0,
            "enabled": False,
        }

    score = compute_candle_context_score(candles, signal)
    if score >= 70:
        bonus = float(V7_CANDLE_CONTEXT_MAX_BONUS)
        weight_bonus = 1
    elif score >= 50:
        bonus = float(V7_CANDLE_CONTEXT_MAX_BONUS) * 0.5
        weight_bonus = 1
    elif score >= 35:
        bonus = float(V7_CANDLE_CONTEXT_MAX_BONUS) * 0.25
        weight_bonus = 0
    else:
        bonus = 0.0
        weight_bonus = 0

    components = {
        "momentum_5": round(score_momentum_buildup(candles, signal, 5), 2),
        "momentum_10": round(score_momentum_buildup(candles, signal, 10), 2),
        "momentum_20": round(score_momentum_buildup(candles, signal, 20), 2),
        "rejection_10": round(score_repeated_rejection(candles, signal, 10), 2),
        "absorption_10": round(score_absorption(candles, signal, 10), 2),
        "break_20": round(score_break_attempts(candles, signal, 20), 2),
    }

    print(
        f"[FER3ON AI V2] CANDLE_CONTEXT: score={score}"
        f" | bonus=+{bonus:.1f}"
        f" | weight+={weight_bonus}"
    )

    return {
        "candle_context_score": score,
        "confidence_bonus": round(bonus, 2),
        "weight_bonus": weight_bonus,
        "components": components,
        "enabled": True,
    }
