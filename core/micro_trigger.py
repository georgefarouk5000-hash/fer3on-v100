# =========================================
# FER3ON V7 — MICRO TRIGGER ENGINE
# M1 timing only — never changes higher-TF bias
# Supports dict candles and MT5 numpy.void records
# =========================================

from core.settings import V7_MICRO_TRIGGER_ENABLED


def candle_value(candle, key, default=0):
    """
    Supports:
    - dict
    - numpy.void
    - namedtuple
    - object attributes
    """
    try:
        if isinstance(candle, dict):
            return candle.get(key, default)

        if hasattr(candle, "dtype") and getattr(candle.dtype, "names", None):
            if key in candle.dtype.names:
                return candle[key]

        if hasattr(candle, key):
            return getattr(candle, key)

        return default

    except Exception:
        return default


def candle_open(c):
    return float(candle_value(c, "open", 0))


def candle_close(c):
    return float(candle_value(c, "close", 0))


def candle_high(c):
    return float(candle_value(c, "high", 0))


def candle_low(c):
    return float(candle_value(c, "low", 0))


def _no_candles(candles):
    """Safe empty check for list or numpy.ndarray."""
    if candles is None:
        return True
    try:
        return len(candles) == 0
    except Exception:
        return True


def _body(c):
    return abs(candle_close(c) - candle_open(c))


def _range(c):
    return candle_high(c) - candle_low(c)


def detect_rejection_candle(candles, direction):
    """Pin bar / rejection wick in signal direction."""
    if _no_candles(candles):
        return False
    c = candles[-1]
    rng = _range(c)
    if rng <= 0:
        return False
    close = candle_close(c)
    open_ = candle_open(c)
    high = candle_high(c)
    low = candle_low(c)
    upper = high - max(open_, close)
    lower = min(open_, close) - low
    if direction == "BUY":
        return lower / rng >= 0.55 and upper / rng <= 0.25
    if direction == "SELL":
        return upper / rng >= 0.55 and lower / rng <= 0.25
    return False


def detect_micro_bos(candles, direction, lookback=8):
    """Micro break of structure on M1."""
    if _no_candles(candles) or len(candles) < lookback + 2:
        return False
    window = candles[-lookback - 1:-1]
    swing_high = max(candle_high(c) for c in window)
    swing_low = min(candle_low(c) for c in window)
    close = candle_close(candles[-1])
    if direction == "BUY":
        return close > swing_high
    if direction == "SELL":
        return close < swing_low
    return False


def detect_momentum_burst(candles, direction):
    """Three consecutive directional bodies with expansion."""
    if _no_candles(candles) or len(candles) < 4:
        return False
    last3 = candles[-3:]
    bodies = [candle_close(c) - candle_open(c) for c in last3]
    if direction == "BUY":
        if not all(b > 0 for b in bodies):
            return False
    elif direction == "SELL":
        if not all(b < 0 for b in bodies):
            return False
    else:
        return False
    return _range(last3[-1]) >= _range(last3[0]) * 0.9


def detect_volume_spike(candles):
    """Tick-volume spike vs recent average (MT5 tick volume)."""
    if _no_candles(candles) or len(candles) < 6:
        return False

    vols = [
        float(
            candle_value(
                c,
                "tick_volume",
                candle_value(c, "real_volume", 0),
            ) or 0
        )
        for c in candles[-6:]
    ]

    if max(vols[:-1]) <= 0:
        return False

    avg_vol = sum(vols[:-1]) / max(len(vols[:-1]), 1)
    current = vols[-1]

    return current > avg_vol * 1.5


def detect_fast_rejection(candles, direction):
    """Quick rejection: large wick + close back inside prior range."""
    if _no_candles(candles) or len(candles) < 3:
        return False
    prev = candles[-2]
    cur = candles[-1]
    prev_mid = (candle_high(prev) + candle_low(prev)) / 2
    if direction == "BUY":
        return candle_low(cur) < candle_low(prev) and candle_close(cur) > prev_mid
    if direction == "SELL":
        return candle_high(cur) > candle_high(prev) and candle_close(cur) < prev_mid
    return False


def _compute_trigger_score(signals):
    """Score 0–100 from active micro-trigger count."""
    if not signals:
        return 0
    active = sum(1 for v in signals.values() if v)
    return int(round(active / len(signals) * 100))


def _build_result(signals, enabled=True, reason=""):
    confirmed = any(signals.values())
    active = [k for k, v in signals.items() if v]
    score = _compute_trigger_score(signals)
    return {
        "confirmed": confirmed,
        "micro_trigger_confirmed": confirmed,
        "score": score,
        "signals": signals,
        "active_triggers": active,
        "enabled": enabled,
        "reason": reason,
    }


def evaluate_micro_triggers(m1_candles, direction):
    """
    Evaluate all M1 micro triggers.
    direction must come from H4/H1/M15/M5 — M1 never sets bias.
    """
    if not _no_candles(m1_candles):
        print(
            f"[MICRO] CandleType={type(m1_candles[-1]).__name__}"
        )

    signals = {
        "rejection_candle": detect_rejection_candle(m1_candles, direction),
        "micro_bos": detect_micro_bos(m1_candles, direction),
        "momentum_burst": detect_momentum_burst(m1_candles, direction),
        "volume_spike": detect_volume_spike(m1_candles),
        "fast_rejection": detect_fast_rejection(m1_candles, direction),
    }
    return _build_result(signals, enabled=V7_MICRO_TRIGGER_ENABLED)


def check_micro_trigger(m1_candles, direction):
    """Public API — returns MICRO_TRIGGER_CONFIRMED bool + details."""
    if not V7_MICRO_TRIGGER_ENABLED:
        return {
            "confirmed": True,
            "micro_trigger_confirmed": True,
            "score": 100,
            "signals": {},
            "active_triggers": ["disabled"],
            "enabled": False,
            "reason": "DISABLED",
        }

    try:
        result = evaluate_micro_triggers(m1_candles, direction)
        print(
            f"[MICRO] Trigger={result['confirmed']} "
            f"Score={result['score']}"
        )
        print(
            f"[FER3ON AI V2] MICRO_TRIGGER {'OK' if result['confirmed'] else 'WAIT'}"
            f" | dir={direction}"
            f" | active={result['active_triggers']}"
        )
        return result
    except Exception as e:
        print(f"[MICRO] ERROR: {e}")
        return {
            "confirmed": False,
            "micro_trigger_confirmed": False,
            "score": 0,
            "signals": {},
            "active_triggers": [],
            "enabled": True,
            "reason": "MICRO_TRIGGER_ERROR",
        }
