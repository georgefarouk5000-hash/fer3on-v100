# =========================================
# FER3ON V7 — SWEEP PREDICTOR
# Confidence bonus only — never direct entry
# =========================================

from core.settings import V7_SWEEP_PREDICTOR_ENABLED, V7_SWEEP_MAX_BONUS


def _distance_score(distance_points, near=15, mid=30):
    if distance_points <= near:
        return 25.0
    if distance_points <= mid:
        return 15.0
    if distance_points <= 50:
        return 8.0
    return 0.0


def _session_sweep_bias(session):
    session = str(session or "UNKNOWN").upper()
    if session in ("LONDON", "OVERLAP"):
        return 20.0
    if session == "NEWYORK":
        return 15.0
    if session == "ASIA":
        return 8.0
    return 5.0


def compute_sweep_probability(
    signal,
    equal_highs,
    equal_lows,
    liquidity_pools,
    current_price,
    session,
    distance_to_pool=None,
):
    """
    SWEEP_PROBABILITY 0–100.
    Estimates likelihood of future liquidity sweep in signal direction.
    """
    if not V7_SWEEP_PREDICTOR_ENABLED:
        return {
            "sweep_probability": 0.0,
            "confidence_bonus": 0.0,
            "enabled": False,
        }

    signal = str(signal or "NONE").upper()
    price = float(current_price or 0)
    if price <= 0 or signal not in ("BUY", "SELL"):
        return {
            "sweep_probability": 0.0,
            "confidence_bonus": 0.0,
            "enabled": True,
        }

    score = 0.0
    equal_highs = equal_highs or []
    equal_lows = equal_lows or []
    pools = liquidity_pools or []

    if signal == "BUY" and equal_lows:
        dist = min(abs(price - lv) for lv in equal_lows)
        score += _distance_score(dist)
    elif signal == "SELL" and equal_highs:
        dist = min(abs(price - hv) for hv in equal_highs)
        score += _distance_score(dist)

    if pools:
        aligned = []
        for p in pools:
            try:
                level = float(p)
            except (TypeError, ValueError):
                continue
            if signal == "BUY" and level < price:
                aligned.append(abs(price - level))
            elif signal == "SELL" and level > price:
                aligned.append(abs(level - price))
        if aligned:
            score += _distance_score(min(aligned))

    if distance_to_pool is not None:
        score += _distance_score(float(distance_to_pool))

    score += _session_sweep_bias(session)
    probability = round(min(100.0, score), 2)

    if probability >= 70:
        bonus = float(V7_SWEEP_MAX_BONUS)
    elif probability >= 50:
        bonus = float(V7_SWEEP_MAX_BONUS) * 0.6
    elif probability >= 35:
        bonus = float(V7_SWEEP_MAX_BONUS) * 0.3
    else:
        bonus = 0.0

    result = {
        "sweep_probability": probability,
        "confidence_bonus": round(bonus, 2),
        "enabled": True,
    }

    print(
        f"[V7] SWEEP_PREDICTOR: prob={probability}"
        f" | bonus=+{bonus:.1f}"
    )
    return result
