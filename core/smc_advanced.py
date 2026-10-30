# =========================================
# FER3ON V5.8 — ADVANCED SMC ENGINE
# Real FVG + Mitigation + Breaker + Premium/Discount
# =========================================

from statistics import median


def _range(candle):
    return max(float(candle["high"]) - float(candle["low"]), 0.0)


def _body(candle):
    return abs(float(candle["close"]) - float(candle["open"]))


def _is_bullish(candle):
    return float(candle["close"]) > float(candle["open"])


def _is_bearish(candle):
    return float(candle["close"]) < float(candle["open"])


def _median_range(rates, sample=20):
    clean = [_range(c) for c in rates[-sample:] if _range(c) > 0]
    return median(clean) if clean else 1.0


def _inside_zone(price, zone):
    if not zone:
        return False
    low = min(float(zone[0]), float(zone[1]))
    high = max(float(zone[0]), float(zone[1]))
    return low <= float(price) <= high


def detect_real_fvg(rates, lookback=40, min_gap_factor=0.18):
    if rates is None or len(rates) < 5:
        return {"type": "NONE", "zone": None, "score": 0, "filled": False}

    current_price = float(rates[-1]["close"])
    median_rng = _median_range(rates, sample=min(len(rates), 20))

    best = {"type": "NONE", "zone": None, "score": 0, "filled": False}
    start = max(0, len(rates) - lookback - 3)
    # Keep the latest candle available only for a retest of an older gap.
    end = len(rates) - 3

    for i in range(start, end):
        c0, c1, c2 = rates[i], rates[i + 1], rates[i + 2]
        impulse_ratio = _range(c1) / max(median_rng, 1e-9)
        if impulse_ratio < 1.25:
            continue

        if float(c2["low"]) > float(c0["high"]):
            zone = (float(c0["high"]), float(c2["low"]))
            gap = zone[1] - zone[0]
            if gap < median_rng * min_gap_factor:
                continue
            filled = current_price < zone[0]
            score = 58 + min((impulse_ratio - 1.0) * 12, 16)
            if _inside_zone(current_price, zone):
                score += 16
            best = max(best, {
                "type": "BUY_FVG",
                "zone": zone,
                "gap_size": round(gap, 3),
                "score": round(min(score, 100), 1),
                "filled": filled,
                "impulse_ratio": round(impulse_ratio, 3),
            }, key=lambda x: x.get("score", 0))

        if float(c2["high"]) < float(c0["low"]):
            zone = (float(c2["high"]), float(c0["low"]))
            gap = zone[1] - zone[0]
            if gap < median_rng * min_gap_factor:
                continue
            filled = current_price > zone[1]
            score = 58 + min((impulse_ratio - 1.0) * 12, 16)
            if _inside_zone(current_price, zone):
                score += 16
            best = max(best, {
                "type": "SELL_FVG",
                "zone": zone,
                "gap_size": round(gap, 3),
                "score": round(min(score, 100), 1),
                "filled": filled,
                "impulse_ratio": round(impulse_ratio, 3),
            }, key=lambda x: x.get("score", 0))

    return best


def detect_mitigation_block(rates, lookback=50):
    if rates is None or len(rates) < 8:
        return {"type": "NONE", "zone": None, "score": 0}

    current_price = float(rates[-1]["close"])
    median_rng = _median_range(rates)
    best = {"type": "NONE", "zone": None, "score": 0}

    for i in range(max(2, len(rates) - lookback), len(rates) - 4):
        pivot = rates[i]
        impulse = rates[i + 1:i + 4]
        impulse_ok_buy = _is_bearish(pivot) and all(_is_bullish(c) for c in impulse)
        impulse_ok_sell = _is_bullish(pivot) and all(_is_bearish(c) for c in impulse)
        impulse_range = sum(_range(c) for c in impulse)
        if impulse_range < median_rng * 2.2:
            continue

        zone = (float(pivot["low"]), float(pivot["high"]))
        score = 54 + min((impulse_range / max(median_rng, 1e-9) - 2.0) * 4, 14)
        if _inside_zone(current_price, zone):
            score += 18

        if impulse_ok_buy:
            best = max(best, {
                "type": "BUY_MITIGATION",
                "zone": zone,
                "score": round(min(score, 100), 1),
            }, key=lambda x: x.get("score", 0))
        elif impulse_ok_sell:
            best = max(best, {
                "type": "SELL_MITIGATION",
                "zone": zone,
                "score": round(min(score, 100), 1),
            }, key=lambda x: x.get("score", 0))

    return best


def detect_breaker_block(rates, lookback=60):
    if rates is None or len(rates) < 10:
        return {"type": "NONE", "zone": None, "score": 0}

    current_price = float(rates[-1]["close"])
    median_rng = _median_range(rates)
    best = {"type": "NONE", "zone": None, "score": 0}

    for i in range(max(3, len(rates) - lookback), len(rates) - 4):
        pivot = rates[i]
        c1, c2, c3 = rates[i + 1], rates[i + 2], rates[i + 3]
        zone = (float(pivot["low"]), float(pivot["high"]))

        bullish_breaker = _is_bearish(pivot) and _is_bearish(c1) and _is_bullish(c2) and float(c2["close"]) > float(pivot["high"])
        bearish_breaker = _is_bullish(pivot) and _is_bullish(c1) and _is_bearish(c2) and float(c2["close"]) < float(pivot["low"])

        expansion = (_range(c1) + _range(c2) + _range(c3)) / max(median_rng, 1e-9)
        if expansion < 3.0:
            continue

        score = 52 + min((expansion - 3.0) * 4, 16)
        if _inside_zone(current_price, zone):
            score += 16

        if bullish_breaker:
            best = max(best, {
                "type": "BUY_BREAKER",
                "zone": zone,
                "score": round(min(score, 100), 1),
            }, key=lambda x: x.get("score", 0))
        elif bearish_breaker:
            best = max(best, {
                "type": "SELL_BREAKER",
                "zone": zone,
                "score": round(min(score, 100), 1),
            }, key=lambda x: x.get("score", 0))

    return best


def compute_premium_discount_zone(rates, current_price=None, lookback=60):
    if rates is None or len(rates) < 10:
        return {
            "equilibrium": 0.0,
            "swing_high": 0.0,
            "swing_low": 0.0,
            "zone": "NEUTRAL",
            "score": 0,
        }

    window = rates[-lookback:]
    swing_high = max(float(c["high"]) for c in window)
    swing_low = min(float(c["low"]) for c in window)
    if current_price is None:
        current_price = float(window[-1]["close"])

    eq = swing_low + (swing_high - swing_low) / 2.0
    zone = "PREMIUM" if current_price > eq else "DISCOUNT"
    deviation = abs(current_price - eq) / max((swing_high - swing_low), 1e-9)
    score = round(min(35 + deviation * 90, 85), 1)

    return {
        "equilibrium": round(eq, 3),
        "swing_high": round(swing_high, 3),
        "swing_low": round(swing_low, 3),
        "zone": zone,
        "score": score,
    }


def analyze_smc_advanced(rates_h1, rates_m5, signal=None):
    pd = compute_premium_discount_zone(rates_h1)
    fvg = detect_real_fvg(rates_m5)
    mitigation = detect_mitigation_block(rates_m5)
    breaker = detect_breaker_block(rates_m5)

    buy_score = 0.0
    sell_score = 0.0
    patterns = []

    if fvg.get("type") == "BUY_FVG":
        buy_score += 2.5 + fvg.get("score", 0) / 40.0
        patterns.append(f"REAL_FVG_BUY:{fvg.get('zone')}")
    elif fvg.get("type") == "SELL_FVG":
        sell_score += 2.5 + fvg.get("score", 0) / 40.0
        patterns.append(f"REAL_FVG_SELL:{fvg.get('zone')}")

    if mitigation.get("type") == "BUY_MITIGATION":
        buy_score += 2.0 + mitigation.get("score", 0) / 45.0
        patterns.append(f"MITIGATION_BUY:{mitigation.get('zone')}")
    elif mitigation.get("type") == "SELL_MITIGATION":
        sell_score += 2.0 + mitigation.get("score", 0) / 45.0
        patterns.append(f"MITIGATION_SELL:{mitigation.get('zone')}")

    if breaker.get("type") == "BUY_BREAKER":
        buy_score += 1.8 + breaker.get("score", 0) / 48.0
        patterns.append(f"BREAKER_BUY:{breaker.get('zone')}")
    elif breaker.get("type") == "SELL_BREAKER":
        sell_score += 1.8 + breaker.get("score", 0) / 48.0
        patterns.append(f"BREAKER_SELL:{breaker.get('zone')}")

    if pd.get("zone") == "DISCOUNT":
        buy_score += 1.4
        patterns.append(f"PD_ZONE:DISCOUNT@{pd.get('equilibrium')}")
    elif pd.get("zone") == "PREMIUM":
        sell_score += 1.4
        patterns.append(f"PD_ZONE:PREMIUM@{pd.get('equilibrium')}")

    if signal == "BUY" and pd.get("zone") == "DISCOUNT":
        buy_score += 0.8
    elif signal == "SELL" and pd.get("zone") == "PREMIUM":
        sell_score += 0.8

    return {
        "buy_score": round(buy_score, 2),
        "sell_score": round(sell_score, 2),
        "patterns": patterns,
        "premium_discount": pd,
        "fvg": fvg,
        "mitigation": mitigation,
        "breaker": breaker,
    }
