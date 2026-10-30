# =========================================
# FER3ON V6 Recovery+ — SMC ARBITRATION LAYER
# Detects exceptionally strong SMC vs opposing bias
# Never bypasses risk engine or hard stops
# =========================================

from typing import Any, Dict, List, Optional

from core.settings import (
    V7_PLUS_ENABLED,
    V7_SMC_ARBITRATION_ENABLED,
    V7_SMC_ARBITRATION_MAX_BONUS,
    V7_SMC_ARBITRATION_MIN_SCORE,
    V7_SMC_ARBITRATION_RATIO,
    SMC_MIN_SCORE,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def compute_smc_scores(
    smc_signal: str,
    smc_strength: float,
    smc_patterns: Optional[List[str]] = None,
    buy_score: Optional[float] = None,
    sell_score: Optional[float] = None,
) -> Dict[str, float]:
    """
    Derive BUY/SELL SMC scores from signal strength or explicit scores.

    When buy_score/sell_score are provided (from SMC engine raw output),
    use them directly. Otherwise infer from signal direction.
    """
    if buy_score is not None and sell_score is not None:
        return {
            "buy": _safe_float(buy_score),
            "sell": _safe_float(sell_score),
        }

    strength = _safe_float(smc_strength)
    signal = str(smc_signal or "NONE").upper()
    if signal == "BUY":
        return {"buy": strength, "sell": 0.0}
    if signal == "SELL":
        return {"sell": strength, "buy": 0.0}
    return {"buy": 0.0, "sell": 0.0}


def is_smc_dominant(buy_score: float, sell_score: float, ratio: float = None) -> Optional[str]:
    """
    Return dominant SMC direction when one side >= ratio × opposing side
    and meets minimum score threshold.
    """
    ratio = float(ratio or V7_SMC_ARBITRATION_RATIO)
    min_score = float(V7_SMC_ARBITRATION_MIN_SCORE)
    buy = _safe_float(buy_score)
    sell = _safe_float(sell_score)

    if buy >= min_score and buy >= ratio * max(sell, 0.01):
        return "BUY"
    if sell >= min_score and sell >= ratio * max(buy, 0.01):
        return "SELL"
    return None


def count_opposing_biases(
    smc_direction: str,
    daily_bias: str,
    structure_bias: str,
    liquidity_bias: str,
    mtf_direction: str,
) -> Dict[str, Any]:
    """Count higher-TF biases opposing the SMC-dominant direction."""
    smc_dir = str(smc_direction or "NONE").upper()
    opposing = []
    aligned = []

    checks = [
        ("daily_bias", str(daily_bias or "NONE").upper()),
        ("structure_bias", str(structure_bias or "NONE").upper()),
        ("liquidity_bias", str(liquidity_bias or "NONE").upper()),
        ("mtf_direction", str(mtf_direction or "NONE").upper()),
    ]

    for name, bias in checks:
        if bias in ("NONE", "NEUTRAL", ""):
            continue
        if bias == smc_dir:
            aligned.append(name)
        else:
            opposing.append(name)

    return {
        "opposing": opposing,
        "aligned": aligned,
        "opposing_count": len(opposing),
        "aligned_count": len(aligned),
    }


def compute_smc_arbitration_score(
    dominant_score: float,
    opposing_score: float,
    opposing_bias_count: int,
    ratio: float,
) -> float:
    """
    SMC_ARBITRATION_SCORE 0–100.
    Higher when SMC is strongly dominant against multiple opposing biases.
    """
    dom = _safe_float(dominant_score)
    opp = _safe_float(opposing_score)
    if dom <= 0:
        return 0.0

    ratio_factor = min(1.0, dom / max(opp, 0.01) / float(ratio))
    score_factor = min(1.0, dom / max(float(SMC_MIN_SCORE) * 3, 1.0))
    conflict_factor = min(1.0, opposing_bias_count / 3.0)

    raw = (ratio_factor * 0.45 + score_factor * 0.35 + conflict_factor * 0.20) * 100
    return round(min(100.0, max(0.0, raw)), 2)


def smc_arbitration_confidence_bonus(arbitration_score: float) -> float:
    """Map arbitration score to confidence bonus (max +10)."""
    if not V7_PLUS_ENABLED or not V7_SMC_ARBITRATION_ENABLED:
        return 0.0
    score = _safe_float(arbitration_score)
    max_bonus = float(V7_SMC_ARBITRATION_MAX_BONUS)
    if score >= 80:
        return max_bonus
    if score >= 65:
        return round(max_bonus * 0.75, 2)
    if score >= 50:
        return round(max_bonus * 0.50, 2)
    if score >= 35:
        return round(max_bonus * 0.25, 2)
    return 0.0


def conflict_penalty_reduction(arbitration_score: float, classification: str) -> float:
    """
    Reduce final-brain conflict penalty when SMC arbitration is active.
    Max reduction = 6 points.
    """
    if classification != "COUNTER_TREND_OPPORTUNITY":
        return 0.0
    score = _safe_float(arbitration_score)
    if score >= 70:
        return 6.0
    if score >= 50:
        return 4.0
    if score >= 35:
        return 2.0
    return 0.0


def analyze_smc_arbitration(
    smc_signal: str,
    smc_strength: float,
    signal: str,
    daily_bias: str,
    structure_bias: str,
    liquidity_bias: str,
    mtf_direction: str,
    smc_patterns: Optional[List[str]] = None,
    buy_score: Optional[float] = None,
    sell_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Full SMC arbitration analysis.

    Returns classification CONFLICT or COUNTER_TREND_OPPORTUNITY,
    SMC_ARBITRATION_SCORE, and confidence bonus.
    """
    disabled = {
        "enabled": False,
        "classification": "CONFLICT",
        "smc_arbitration_score": 0.0,
        "confidence_bonus": 0.0,
        "conflict_penalty_reduction": 0.0,
        "smc_dominant_direction": None,
        "buy_score": 0.0,
        "sell_score": 0.0,
        "reason": "DISABLED",
    }

    if not V7_PLUS_ENABLED or not V7_SMC_ARBITRATION_ENABLED:
        return disabled

    scores = compute_smc_scores(
        smc_signal, smc_strength, smc_patterns, buy_score, sell_score
    )
    buy = scores["buy"]
    sell = scores["sell"]

    dominant_dir = is_smc_dominant(buy, sell)
    if dominant_dir is None:
        result = {
            "enabled": True,
            "classification": "CONFLICT",
            "smc_arbitration_score": 0.0,
            "confidence_bonus": 0.0,
            "conflict_penalty_reduction": 0.0,
            "smc_dominant_direction": None,
            "buy_score": buy,
            "sell_score": sell,
            "reason": "SMC_NOT_DOMINANT",
        }
        print(
            f"[RECOVERY+] SMC_ARBITRATION: CONFLICT"
            f" | BUY={buy} SELL={sell}"
            f" | reason=SMC_NOT_DOMINANT"
        )
        return result

    dom_score = buy if dominant_dir == "BUY" else sell
    opp_score = sell if dominant_dir == "BUY" else buy

    bias_check = count_opposing_biases(
        dominant_dir, daily_bias, structure_bias, liquidity_bias, mtf_direction
    )
    opposing_count = bias_check["opposing_count"]

    if opposing_count == 0:
        classification = "ALIGNED"
        reason = "NO_OPPOSING_BIAS"
    else:
        classification = "COUNTER_TREND_OPPORTUNITY"
        reason = f"OPPOSING={bias_check['opposing']}"

    arb_score = compute_smc_arbitration_score(
        dom_score, opp_score, opposing_count, V7_SMC_ARBITRATION_RATIO
    )
    bonus = smc_arbitration_confidence_bonus(arb_score) if classification == "COUNTER_TREND_OPPORTUNITY" else 0.0
    penalty_reduction = conflict_penalty_reduction(arb_score, classification)

    signal_dir = str(signal or "NONE").upper()
    if signal_dir not in ("BUY", "SELL") or signal_dir != dominant_dir:
        bonus = 0.0
        penalty_reduction = 0.0
        if signal_dir in ("BUY", "SELL") and signal_dir != dominant_dir:
            reason = f"SIGNAL_MISMATCH:{signal_dir}!={dominant_dir}"

    result = {
        "enabled": True,
        "classification": classification,
        "smc_arbitration_score": arb_score,
        "confidence_bonus": bonus,
        "conflict_penalty_reduction": penalty_reduction,
        "smc_dominant_direction": dominant_dir,
        "buy_score": buy,
        "sell_score": sell,
        "opposing_biases": bias_check["opposing"],
        "aligned_biases": bias_check["aligned"],
        "reason": reason,
    }

    print(
        f"[RECOVERY+] SMC_ARBITRATION: {classification}"
        f" | score={arb_score}"
        f" | dir={dominant_dir}"
        f" | BUY={buy} SELL={sell}"
        f" | bonus=+{bonus}"
        f" | penalty_red=-{penalty_reduction}"
        f" | {reason}"
    )
    return result
