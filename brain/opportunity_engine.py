# =========================================
# FER3ON V7 — OPPORTUNISTIC ENTRY ENGINE
# Reduced-risk entries when setup is good but not perfect
# =========================================

from core.settings import (
    V7_OPPORTUNITY_ENGINE_ENABLED,
    V7_OPPORTUNITY_MIN_CONFIDENCE,
    V7_OPPORTUNITY_QUARTER_MAX,
    V7_OPPORTUNITY_HALF_MAX,
)


OPPORTUNITY_SESSIONS = {"LONDON", "NEWYORK", "NEW_YORK", "OVERLAP"}


def is_mtf_aligned(mtf_direction, signal):
    return mtf_direction == signal and signal in ("BUY", "SELL")


def is_liquidity_aligned(liquidity_bias, signal):
    if liquidity_bias in ("NONE", "NEUTRAL", None):
        return False
    return liquidity_bias == signal


def is_opportunity_session(session, hour=None):
    session = str(session or "UNKNOWN").upper()
    if session in OPPORTUNITY_SESSIONS:
        return True
    if hour is not None:
        from core.dynamic_confidence import is_overlap_session
        return is_overlap_session(hour)
    return False


def classify_opportunity_entry(confidence_pct):
    """
    Confidence 55–69 → ENTER_QUARTER (25% lot)
    Confidence 70–79 → ENTER_HALF (50% lot)
    Below min or >= 80 → NONE (use normal path)
    """
    conf = float(confidence_pct or 0)
    q_min = float(V7_OPPORTUNITY_MIN_CONFIDENCE)
    q_max = float(V7_OPPORTUNITY_QUARTER_MAX)
    h_max = float(V7_OPPORTUNITY_HALF_MAX)
    if conf < 50:
        return "ENTER_QUARTER"
    if conf < 70:
        return "ENTER_QUARTER"
    if conf < 80:
        return "ENTER_HALF"
    return "NONE"


def evaluate_opportunity(
    signal,
    confidence_pct,
    mtf_direction,
    liquidity_bias,
    session,
    market_regime,
    hour=None,
    risk_blocked=False,
    crisis_active=False,
):
    """
    Opportunistic entry evaluation.
    Never overrides daily loss, drawdown, or crisis protection.
    """
    if not V7_OPPORTUNITY_ENGINE_ENABLED:
        return {"action": "NONE", "reason": "V7_OPPORTUNITY_DISABLED", "enabled": False}

    if risk_blocked or crisis_active:
        return {
            "action": "NONE",
            "reason": "RISK_OR_CRISIS_BLOCKED",
            "enabled": True,
        }

    if signal not in ("BUY", "SELL"):
        return {"action": "NONE", "reason": "NO_SIGNAL", "enabled": True}

    if not is_mtf_aligned(mtf_direction, signal):
        return {"action": "NONE", "reason": "MTF_NOT_ALIGNED", "enabled": True}

    if not is_liquidity_aligned(liquidity_bias, signal):
        return {"action": "NONE", "reason": "LIQUIDITY_NOT_ALIGNED", "enabled": True}

    if not is_opportunity_session(session, hour):
        return {"action": "NONE", "reason": "SESSION_NOT_ELIGIBLE", "enabled": True}

    conf = float(confidence_pct or 0)
    min_conf = float(V7_OPPORTUNITY_MIN_CONFIDENCE)

    if conf < min_conf:
        return {
            "action": "NONE",
            "reason": f"CONF_BELOW_MIN:{conf}<{min_conf}",
            "min_confidence": min_conf,
            "enabled": True,
        }

    action = classify_opportunity_entry(conf)
    if action == "NONE":
        return {
            "action": "NONE",
            "reason": f"CONF_OUTSIDE_OPPORTUNITY_BAND:{conf}",
            "min_confidence": min_conf,
            "enabled": True,
        }

    lot_mult = 0.25 if action == "ENTER_QUARTER" else 0.50

    print(
        f"[FER3ON AI V2] OPPORTUNITY_ENGINE: {action}"
        f" | conf={conf}"
        f" | min={min_conf}"
        f" | lot_mult={lot_mult}"
    )

    return {
        "action": action,
        "lot_mult": lot_mult,
        "min_confidence": min_conf,
        "confidence_pct": conf,
        "reason": f"OPPORTUNITY_{action}",
        "enabled": True,
    }
