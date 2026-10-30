# =========================================
# FER3ON V5.8 — PROFESSIONAL CANDLE ENGINE
# Strength-based candle intelligence (0-100)
# =========================================

from statistics import median

from core.candle_patterns import (
    detect_engulfing,
    detect_pin_bar,
    detect_inside_bar,
    detect_morning_star,
    detect_evening_star,
    detect_three_white_soldiers,
    detect_three_black_crows,
)


def _body(candle):
    return abs(float(candle["close"]) - float(candle["open"]))


def _range(candle):
    return max(float(candle["high"]) - float(candle["low"]), 0.0)


def _upper_wick(candle):
    return max(float(candle["high"]) - max(float(candle["open"]), float(candle["close"])), 0.0)


def _lower_wick(candle):
    return max(min(float(candle["open"]), float(candle["close"])) - float(candle["low"]), 0.0)


def _is_bullish(candle):
    return float(candle["close"]) > float(candle["open"])


def _is_bearish(candle):
    return float(candle["close"]) < float(candle["open"])


def _safe_median(values, default=1.0):
    clean = [float(v) for v in values if float(v) > 0]
    return median(clean) if clean else default


def _price_location_score(last, swing_high, swing_low, direction):
    span = max(float(swing_high) - float(swing_low), 1e-9)
    eq = float(swing_low) + span / 2.0
    close = float(last["close"])

    if direction == "BUY":
        if close <= eq:
            return 8, "discount_zone"
        if close <= eq + span * 0.1:
            return 4, "near_equilibrium"
        return -4, "premium_zone"

    if direction == "SELL":
        if close >= eq:
            return 8, "premium_zone"
        if close >= eq - span * 0.1:
            return 4, "near_equilibrium"
        return -4, "discount_zone"

    return 0, "neutral_zone"


def strength_to_weight(strength):
    strength = float(strength or 0)
    if strength >= 85:
        return 4
    if strength >= 70:
        return 3
    if strength >= 55:
        return 2
    if strength >= 35:
        return 1
    return 0


def _score_single_pattern(pattern_name, direction, rates, signal=None, context=None):
    context = context or {}
    if rates is None or len(rates) < 3 or direction not in ("BUY", "SELL"):
        return None

    last = rates[-1]
    prev = rates[-2]
    body = _body(last)
    rng = _range(last)
    upper = _upper_wick(last)
    lower = _lower_wick(last)
    median_range = _safe_median([_range(c) for c in rates[-8:]], default=max(rng, 1.0))
    median_body = _safe_median([_body(c) for c in rates[-8:]], default=max(body, 1.0))
    range_expansion = rng / max(median_range, 1e-9)
    body_expansion = body / max(median_body, 1e-9)
    body_ratio = body / max(rng, 1e-9)
    wick_dom = max(upper, lower) / max(body, 1e-9)
    reasons = []

    base_map = {
        "ENGULFING": 56,
        "PIN_BAR": 52,
        "INSIDE_BAR": 34,
        "MORNING_STAR": 72,
        "EVENING_STAR": 72,
        "THREE_WHITE_SOLDIERS": 78,
        "THREE_BLACK_CROWS": 78,
    }
    score = float(base_map.get(pattern_name, 45))

    if pattern_name == "ENGULFING":
        prev_body = _body(prev)
        engulf_ratio = body / max(prev_body, 1e-9)
        score += min((engulf_ratio - 1.0) * 18, 16)
        if direction == "BUY" and _is_bearish(prev) and _is_bullish(last):
            score += 5
            reasons.append("clean_bullish_engulf")
        elif direction == "SELL" and _is_bullish(prev) and _is_bearish(last):
            score += 5
            reasons.append("clean_bearish_engulf")

    elif pattern_name == "PIN_BAR":
        dominant_wick = lower if direction == "BUY" else upper
        wick_ratio = dominant_wick / max(rng, 1e-9)
        score += min((wick_ratio - 0.45) * 40, 18)
        score += min((wick_dom - 2.0) * 3.5, 10)
        reasons.append("rejection_wick")

    elif pattern_name == "INSIDE_BAR":
        mother = rates[-2]
        mother_range = _range(mother)
        compression = rng / max(mother_range, 1e-9)
        score += max((0.55 - compression) * 35, 0)
        reasons.append("volatility_compression")

    elif pattern_name in ("MORNING_STAR", "EVENING_STAR"):
        trio_range = sum(_range(c) for c in rates[-3:]) / 3.0
        score += min((trio_range / max(median_range, 1e-9) - 1.0) * 10, 12)
        reasons.append("three_candle_reversal")

    elif pattern_name in ("THREE_WHITE_SOLDIERS", "THREE_BLACK_CROWS"):
        closes = [float(c["close"]) for c in rates[-3:]]
        monotonic = closes[2] > closes[1] > closes[0] if direction == "BUY" else closes[2] < closes[1] < closes[0]
        if monotonic:
            score += 10
            reasons.append("sequential_closes")
        score += min((body_expansion - 1.0) * 8, 8)

    if body_ratio >= 0.55:
        score += 7
        reasons.append("strong_body")
    elif body_ratio <= 0.18 and pattern_name != "PIN_BAR":
        score -= 6
        reasons.append("weak_body")

    if range_expansion >= 1.25:
        score += min((range_expansion - 1.0) * 8, 10)
        reasons.append("range_expansion")

    if signal and signal == direction:
        score += 6
        reasons.append("signal_alignment")
    elif signal and signal != direction:
        score -= 8
        reasons.append("signal_conflict")

    if context.get("liquidity_sweep"):
        score += 12
        reasons.append("post_sweep_confluence")

    if context.get("bos_confirmed"):
        score += 8
        reasons.append("bos_confluence")

    if context.get("fvg_retest") or context.get("mitigation_touch"):
        score += 8
        reasons.append("zone_retest_confluence")

    if context.get("volume_ratio", 1.0) >= 1.2:
        score += min((float(context.get("volume_ratio", 1.0)) - 1.0) * 10, 8)
        reasons.append("volume_expansion")

    trend_bias = context.get("trend_bias")
    if trend_bias and trend_bias == direction:
        score += 5
        reasons.append("trend_alignment")
    elif trend_bias and trend_bias not in ("NONE", "NEUTRAL") and trend_bias != direction:
        score -= 5
        reasons.append("trend_conflict")

    swing_high = max(float(c["high"]) for c in rates[-20:])
    swing_low = min(float(c["low"]) for c in rates[-20:])
    loc_score, loc_reason = _price_location_score(last, swing_high, swing_low, direction)
    score += loc_score
    reasons.append(loc_reason)

    strength = max(0, min(100, round(score, 1)))
    return {
        "pattern": pattern_name,
        "direction": direction,
        "strength": strength,
        "weight": strength_to_weight(strength),
        "body_ratio": round(body_ratio, 3),
        "range_expansion": round(range_expansion, 3),
        "reasons": reasons,
    }


def analyze_candle_context(rates, signal=None, context=None):
    context = context or {}
    if rates is None or len(rates) < 3:
        return {
            "pattern": "NONE",
            "direction": "NONE",
            "strength": 0,
            "weight": 0,
            "candidates": [],
            "summary": "NO_CANDLE_DATA",
        }

    last = rates[-1]
    candidates = []

    eng = detect_engulfing(last, rates[-2])
    if eng != "NONE":
        candidates.append(_score_single_pattern("ENGULFING", eng, rates, signal=signal, context=context))

    pin = detect_pin_bar(last)
    if pin != "NONE":
        candidates.append(_score_single_pattern("PIN_BAR", pin, rates, signal=signal, context=context))

    inside = detect_inside_bar(rates)
    if inside == "INSIDE":
        preferred_dir = signal if signal in ("BUY", "SELL") else context.get("trend_bias", "NONE")
        if preferred_dir in ("BUY", "SELL"):
            candidates.append(_score_single_pattern("INSIDE_BAR", preferred_dir, rates, signal=signal, context=context))

    ms = detect_morning_star(rates)
    if ms != "NONE":
        candidates.append(_score_single_pattern("MORNING_STAR", ms, rates, signal=signal, context=context))

    es = detect_evening_star(rates)
    if es != "NONE":
        candidates.append(_score_single_pattern("EVENING_STAR", es, rates, signal=signal, context=context))

    tws = detect_three_white_soldiers(rates)
    if tws != "NONE":
        candidates.append(_score_single_pattern("THREE_WHITE_SOLDIERS", tws, rates, signal=signal, context=context))

    tbc = detect_three_black_crows(rates)
    if tbc != "NONE":
        candidates.append(_score_single_pattern("THREE_BLACK_CROWS", tbc, rates, signal=signal, context=context))

    candidates = [c for c in candidates if c]
    if not candidates:
        return {
            "pattern": "NONE",
            "direction": "NONE",
            "strength": 0,
            "weight": 0,
            "candidates": [],
            "summary": "NO_PATTERN",
        }

    candidates.sort(key=lambda x: (x["strength"], x["weight"]), reverse=True)
    best = candidates[0]
    best["candidates"] = candidates
    best["summary"] = f"{best['pattern']}:{best['direction']}:{best['strength']}"
    return best
