# =========================================
# FER3ON-AI-V3 — ADVANCED SMC (Signal-Layer Wrapper)
# =========================================
# الملف الأساسي smc_advanced.py موجود بالفعل في OPERATIONAL.
# هذا الملف يلعب دور:
#   - signal-layer رفيع المستوى يُصدّر 4 مزايا:
#       * Real FVG                → detect_real_fvg()
#       * Mitigation Block        → detect_mitigation_block()
#       * Breaker Block           → detect_breaker_block()
#       * Premium / Discount Zone → compute_premium_discount_zone()
#   - analyzer موحد analyze_smc_advanced() يعمل backward-compatible.
#
# الهدف: إعطاء main.py / unified_decision.py / Composite
#        entry-point واضح اسمه advanced_smc ليستهلك
#        جميع وظائف SMC المتقدمة بسطر واحد.
# =========================================

from core.smc_advanced import (
    detect_real_fvg,
    detect_mitigation_block,
    detect_breaker_block,
    compute_premium_discount_zone,
    analyze_smc_advanced,
    _range,
    _body,
    _is_bullish,
    _is_bearish,
    _median_range,
    _inside_zone,
)


# =========================================
# V3 EXTENSION — مكافأة موحدة للـ Composite
# =========================================


V3_PATTERN_BOOST = {
    "BUY_BREAKER": 1.8,
    "SELL_BREAKER": 1.8,
    "BUY_MITIGATION": 1.5,
    "SELL_MITIGATION": 1.5,
    "BUY_FVG": 2.0,
    "SELL_FVG": 2.0,
}


def estimate_v3_pattern_bonus(advanced_result: dict) -> float:
    """
    يُرجع مكافأة SMC v3 على أساس نوع النمط المُكتشف.
    مكافأة clamp إلى [0, 6.0].
    """
    if not isinstance(advanced_result, dict):
        return 0.0

    bonus = 0.0
    for key in ("type",):
        kind = str(advanced_result.get(key, "")).upper()
        bonus += float(V3_PATTERN_BOOST.get(kind, 0.0))

    return min(max(bonus, 0.0), 6.0)


def analyze_smc_v3(rates_h1, rates_m5, signal: str = None) -> dict:
    """
    الـ entry-point الموحد لطبقة SMC V3.
    يرجع قاموس غني يمكن أن يُستهلك في unified_decision:
        {
          "grade_bonus": float,
          "advanced_score": float,
          "premium_discount": dict,
          "fvg": dict,
          "mitigation": dict,
          "breaker": dict,
          "patterns": list[str],
        }
    """
    try:
        base = analyze_smc_advanced(rates_h1, rates_m5, signal=signal) or {}
    except Exception as e:
        print(f"⚠️ advanced_smc.analyze_smc_v3 failed: {e}")
        base = {}

    advanced_score = 0.0
    if signal and signal.upper() == "BUY":
        advanced_score = float(base.get("buy_score", 0) or 0)
    elif signal and signal.upper() == "SELL":
        advanced_score = float(base.get("sell_score", 0) or 0)
    else:
        advanced_score = max(
            float(base.get("buy_score", 0) or 0),
            float(base.get("sell_score", 0) or 0),
        )

    fvg = base.get("fvg", {}) or {}
    mitigation = base.get("mitigation", {}) or {}
    breaker = base.get("breaker", {}) or {}

    pattern_bonus = estimate_v3_pattern_bonus(fvg) \
        + estimate_v3_pattern_bonus(mitigation) \
        + estimate_v3_pattern_bonus(breaker)

    base_bonus = pattern_bonus + float(advanced_score) * 0.15

    return {
        "grade_bonus": round(min(base_bonus, 6.0), 2),
        "advanced_score": round(advanced_score, 2),
        "premium_discount": base.get("premium_discount", {}),
        "fvg": fvg,
        "mitigation": mitigation,
        "breaker": breaker,
        "patterns": list(base.get("patterns", []) or []),
    }


__all__ = [
    "detect_real_fvg",
    "detect_mitigation_block",
    "detect_breaker_block",
    "compute_premium_discount_zone",
    "analyze_smc_v3",
    "estimate_v3_pattern_bonus",
]
