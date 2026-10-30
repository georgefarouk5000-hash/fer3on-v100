"""Market DNA engine for market-state classification."""

from __future__ import annotations

from typing import Any, Dict


def analyze_market_dna(
    trend_strength: float = 0.0,
    volatility: float = 0.0,
    recent_body_ratio: float = 0.5,
    wick_ratio: float = 0.0,
    volume_spike: float = 0.0,
    range_expansion: float = 0.0,
    manipulation_score: float = 0.0,
) -> Dict[str, Any]:
    trend_strength = float(trend_strength)
    volatility = float(volatility)
    recent_body_ratio = float(recent_body_ratio)
    wick_ratio = float(wick_ratio)
    volume_spike = float(volume_spike)
    range_expansion = float(range_expansion)
    manipulation_score = float(manipulation_score)

    if trend_strength > 0.7 and recent_body_ratio > 0.65 and wick_ratio < 0.25:
        market_dna_state = "CLEAN_TREND"
    elif manipulation_score > 0.6 and wick_ratio > 0.4:
        market_dna_state = "MANIPULATED_TREND"
    elif range_expansion > 0.6 and volume_spike > 0.5:
        market_dna_state = "VOLATILITY_EXPANSION"
    elif trend_strength < 0.25 and recent_body_ratio < 0.45 and wick_ratio > 0.35:
        market_dna_state = "ALGORITHMIC_RANGING"
    elif volume_spike > 0.7 and wick_ratio > 0.45:
        market_dna_state = "LIQUIDITY_TRAP"
    elif trend_strength > 0.4 and recent_body_ratio < 0.45:
        market_dna_state = "EXHAUSTION"
    elif trend_strength > 0.4:
        market_dna_state = "ACCUMULATION"
    else:
        market_dna_state = "UNKNOWN"

    manipulation_probability = round(max(0.0, min(1.0, manipulation_score)), 3)
    trap_probability = round(max(0.0, min(1.0, 0.25 * wick_ratio + 0.25 * volume_spike + 0.25 * range_expansion + 0.25 * manipulation_score)), 3)
    trend_quality = round(max(0.0, min(1.0, 0.4 * abs(trend_strength) + 0.3 * recent_body_ratio + 0.3 * max(0.0, 1 - wick_ratio))), 3)

    return {
        "market_dna_state": market_dna_state,
        "manipulation_probability": manipulation_probability,
        "trap_probability": trap_probability,
        "trend_quality": trend_quality,
    }
