# =========================================
# FER3ON V6 RECOVERY — LIQUIDITY VACUUM DETECTOR
# Thin zones, fast moves, imbalances
# Supports dict and MT5 numpy.void candles
# =========================================

from core.settings import V7_LIQUIDITY_VACUUM_ENABLED, V7_VACUUM_FAST_EXEC_SCORE
from core.micro_trigger import candle_value, _no_candles


def _range_stats(candles):
    if _no_candles(candles):
        return 0.0, 0.0, 0.0
    ranges = [
        float(candle_value(c, "high", 0)) - float(candle_value(c, "low", 0))
        for c in candles
    ]
    avg = sum(ranges) / len(ranges) if ranges else 0.0
    return avg, min(ranges), max(ranges)


def score_thin_liquidity(candles, atr):
    """Low range candles vs ATR suggest thin liquidity."""
    if _no_candles(candles) or float(atr or 0) <= 0:
        return 0.0
    avg_range, _, _ = _range_stats(candles[-5:])
    ratio = avg_range / float(atr)
    if ratio < 0.35:
        return 35.0
    if ratio < 0.55:
        return 30.0
    if ratio < 0.75:
        return 20.0
    if ratio < 1.0:
        return 15.0
    return 8.0


def score_fast_directional_move(closes, atr):
    """Fast directional displacement."""
    if not closes or len(closes) < 5 or float(atr or 0) <= 0:
        return 0.0
    move = abs(float(closes[-1]) - float(closes[-5]))
    ratio = move / float(atr)
    if ratio > 1.5:
        return 30.0
    if ratio > 1.0:
        return 25.0
    if ratio > 0.6:
        return 15.0
    return 0.0


def score_imbalance(candles):
    """Wick/body imbalance — one-sided rejection."""
    if _no_candles(candles):
        return 0.0
    last = candles[-1]
    body = abs(float(candle_value(last, "close", 0)) - float(candle_value(last, "open", 0)))
    full = float(candle_value(last, "high", 0)) - float(candle_value(last, "low", 0))
    if full <= 0:
        return 0.0
    open_ = float(candle_value(last, "open", 0))
    close = float(candle_value(last, "close", 0))
    high = float(candle_value(last, "high", 0))
    low = float(candle_value(last, "low", 0))
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    wick_ratio = max(upper_wick, lower_wick) / full
    if wick_ratio > 0.55 and body / full < 0.35:
        return 22.0
    if wick_ratio > 0.40:
        return 12.0
    return 0.0


def score_vacuum_structure(candles):
    """Consecutive same-direction bodies with expanding range."""
    if _no_candles(candles) or len(candles) < 4:
        return 0.0
    bodies = []
    for c in candles[-4:]:
        bodies.append(
            float(candle_value(c, "close", 0)) - float(candle_value(c, "open", 0))
        )
    same_dir = all(b > 0 for b in bodies) or all(b < 0 for b in bodies)
    if not same_dir:
        return 0.0
    ranges = [
        float(candle_value(c, "high", 0)) - float(candle_value(c, "low", 0))
        for c in candles[-4:]
    ]
    expanding = ranges[-1] > ranges[0] * 1.1
    return 18.0 if expanding else 10.0


def compute_vacuum_score(candles, closes, atr):
    """
    VACUUM_SCORE 0–100 from structural liquidity features.
    No traditional indicators.
    """
    thin = score_thin_liquidity(candles, atr)
    fast = score_fast_directional_move(closes, atr)
    imb = score_imbalance(candles)
    vac = score_vacuum_structure(candles)
    raw = thin + fast + imb + vac
    return round(min(100.0, raw), 2)


def analyze_liquidity_vacuum(candles, closes, atr, mtf_aligned=False):
    """
    Full vacuum analysis.
    fast_execution_eligible when VACUUM_SCORE > 70 and MTF aligned.
    """
    if not V7_LIQUIDITY_VACUUM_ENABLED:
        return {
            "vacuum_score": 0.0,
            "fast_execution_eligible": False,
            "components": {},
            "enabled": False,
        }

    components = {
        "thin_liquidity": score_thin_liquidity(candles, atr),
        "fast_move": score_fast_directional_move(closes, atr),
        "imbalance": score_imbalance(candles),
        "vacuum_structure": score_vacuum_structure(candles),
    }
    score = compute_vacuum_score(candles, closes, atr)
    fast_eligible = score > V7_VACUUM_FAST_EXEC_SCORE and bool(mtf_aligned)

    result = {
        "vacuum_score": score,
        "fast_execution_eligible": fast_eligible,
        "components": components,
        "enabled": True,
    }

    print(
        f"[FER3ON AI V2] LIQUIDITY_VACUUM: score={score}"
        f" | fast_exec={fast_eligible}"
        f" | mtf_aligned={mtf_aligned}"
    )
    return result
