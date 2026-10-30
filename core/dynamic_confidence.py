# =========================================
# FER3ON V7 — DYNAMIC CONFIDENCE THRESHOLD
# Session-aware thresholds with regime adjustments
# =========================================

from core.settings import (
    V7_DYNAMIC_THRESHOLD_ENABLED,
    V7_THRESHOLD_ASIA,
    V7_THRESHOLD_LONDON,
    V7_THRESHOLD_NEWYORK,
    V7_THRESHOLD_OVERLAP,
    V7_THRESHOLD_VOLATILE_ADJ,
    V7_THRESHOLD_CRISIS_ADJ,
)


def is_overlap_session(hour):
    """London/NY overlap window (UTC)."""
    try:
        h = int(hour)
    except (TypeError, ValueError):
        return False
    return 13 <= h < 16


def get_dynamic_confidence_threshold(session, market_regime="UNKNOWN", hour=None):
    """
    Compute DYNAMIC_THRESHOLD for confidence evaluation.

    Base by session:
      ASIA      = 70
      LONDON    = 55
      NEWYORK   = 58
      OVERLAP   = 52

    Adjustments:
      VOLATILE  +5
      CRISIS    +10
    """
    if not V7_DYNAMIC_THRESHOLD_ENABLED:
        from core.settings import QUALITY_CONFIDENCE_BYPASS
        return {
            "threshold": QUALITY_CONFIDENCE_BYPASS,
            "base": QUALITY_CONFIDENCE_BYPASS,
            "session": session,
            "regime_adj": 0,
            "overlap": False,
            "enabled": False,
        }

    session_key = str(session or "UNKNOWN").upper()
    if hour is not None and is_overlap_session(hour):
        base = V7_THRESHOLD_OVERLAP
        overlap = True
        effective_session = "OVERLAP"
    else:
        overlap = False
        effective_session = session_key
        base_map = {
            "ASIA": V7_THRESHOLD_ASIA,
            "LONDON": V7_THRESHOLD_LONDON,
            "NEWYORK": V7_THRESHOLD_NEWYORK,
            "NEW_YORK": V7_THRESHOLD_NEWYORK,
            "OVERLAP": V7_THRESHOLD_OVERLAP,
        }
        base = base_map.get(session_key, V7_THRESHOLD_LONDON)

    regime_adj = 0
    regime = str(market_regime or "UNKNOWN").upper()
    if regime == "VOLATILE":
        regime_adj += V7_THRESHOLD_VOLATILE_ADJ
    elif regime == "CRISIS":
        regime_adj += V7_THRESHOLD_CRISIS_ADJ

    threshold = min(95, base + regime_adj)

    result = {
        "threshold": threshold,
        "base": base,
        "session": effective_session,
        "regime_adj": regime_adj,
        "overlap": overlap,
        "enabled": True,
    }

    print(
        f"[FER3ON AI V2 THRESHOLD] {threshold}"
        f" | session={effective_session}"
        f" | base={base}"
        f" | regime_adj=+{regime_adj}"
    )
    return result


def confidence_meets_threshold(confidence_pct, session, market_regime="UNKNOWN", hour=None):
    """Return True if confidence_pct >= DYNAMIC_THRESHOLD."""
    dyn = get_dynamic_confidence_threshold(session, market_regime, hour)
    met = float(confidence_pct or 0) >= dyn["threshold"]
    return met, dyn
