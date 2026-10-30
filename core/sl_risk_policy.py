"""Central strategy/regime SL caps used by the adaptive SL/TP pipeline."""

from __future__ import annotations

from typing import Any, Dict, Optional


GLOBAL_SL_HARD_CAP = 15.0
MIN_EFFECTIVE_SL = 3.0

STRATEGY_SL_CAPS = {
    "SMC": 15.0,
    "DAILY": 15.0,
    "MANUAL": 12.0,
}

REGIME_SL_MODIFIERS = {
    "TRENDING": 1.00,
    "RANGING": 0.80,
    "VOLATILE": 0.60,
    "CRISIS": 0.50,
    "UNKNOWN": 0.70,
}


def resolve_sl_cap(
    *,
    strategy: Optional[str] = None,
    market_regime: Optional[str] = None,
    confidence: Any = 0.5,
    exposure_modifier: float = 1.0,
) -> Dict[str, Any]:
    """Return an effective cap; no context can raise the global hard cap."""
    strategy_key = str(strategy or "").upper()
    regime_key = str(market_regime or "UNKNOWN").upper()
    try:
        confidence_ratio = float(confidence)
        if confidence_ratio > 1.0:
            confidence_ratio /= 100.0
    except (TypeError, ValueError):
        confidence_ratio = 0.5
    confidence_ratio = max(0.0, min(1.0, confidence_ratio))
    try:
        exposure = max(0.5, min(1.0, float(exposure_modifier)))
    except (TypeError, ValueError):
        exposure = 0.5

    base_cap = float(STRATEGY_SL_CAPS.get(strategy_key, GLOBAL_SL_HARD_CAP))
    regime_modifier = float(REGIME_SL_MODIFIERS.get(regime_key, 0.70))
    confidence_modifier = max(0.5, min(1.0, confidence_ratio))
    effective_cap = min(
        GLOBAL_SL_HARD_CAP,
        base_cap * regime_modifier * confidence_modifier * exposure,
    )
    effective_cap = max(MIN_EFFECTIVE_SL, effective_cap)
    return {
        "strategy": strategy_key or "UNKNOWN",
        "regime": regime_key,
        "base_cap": base_cap,
        "regime_modifier": regime_modifier,
        "confidence_modifier": confidence_modifier,
        "exposure_modifier": exposure,
        "effective_cap": round(effective_cap, 2),
        "global_hard_cap": GLOBAL_SL_HARD_CAP,
    }