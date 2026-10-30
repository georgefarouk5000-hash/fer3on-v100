# =========================================
# FER3ON-AI-V3 — SMC V3 INTEGRATION (Signal-Layer)
# =========================================
# wrapper رفيع المستوى يجمع:
#   - smc_entry_v4  (entry sequence + grade)
#   - advanced_smc  (FVG + Mitigation + Breaker + PD Zone)
# ثم يستهلك في unified_decision.py كـ soft bonus / penalty
# على Composite، دون كسر الـ 5 محاور الأساسية.
# =========================================

from typing import Any, Dict


# =========================================
# V3 BONUS WEIGHTING (defaults — يُعدل في P4 calibration)
# =========================================

SMC_V3_GRADE_BONUS = {
    "A+": 4.5,
    "A":  3.5,
    "B+": 2.0,
    "B":  1.0,
    "C":  0.3,
    "NONE": 0.0,
}

SMC_V3_ADV_BONUS_MIN = 1.0   # لو advanced_score >= 5
SMC_V3_PD_ALIGN_BONUS = 1.0
SMC_V3_ADV_PATTERN_BONUS = 1.0
SMC_V3_WEIGHT = 0.07

SMC_V3_BONUS_CAP = 7.5
SMC_V3_BONUS_FLOOR = -3.0


def compute_smc_v3_layer(symbol: str, signal: str, rates=None) -> Dict[str, Any]:
    """
    يجمع بين:
      - SMC entry sequence (smc_entry_v4)
      - Advanced SMC (advanced_smc → analyze_smc_v3)
    ويُرجع قاموس موحد يمكن أن يستهلكه Composite كـ bonus / penalty.
    """
    details: Dict[str, Any] = {
        "grade": "NONE",
        "confirmed": False,
        "entry_score": 0,
        "advanced_score": 0.0,
        "grade_bonus": 0.0,
        "smc_v3_bonus": 0.0,
        "patterns": [],
        "weight": SMC_V3_WEIGHT,
    }

    # ----- Entry sequence -----
    try:
        from core.smc_entry_v4 import (
            check_smc_entry_sequence,
            get_v3_grade_bonus,
        )

        confirmed, grade, entry_details = check_smc_entry_sequence(symbol, signal)
        details["grade"] = grade
        details["confirmed"] = bool(confirmed)
        details["entry_score"] = int(entry_details.get("grade_score", 0) or 0)
        details["grade_bonus"] = float(get_v3_grade_bonus(grade))
    except Exception as e:
        print(f"⚠️ SMC V3 entry-sequence failed: {e}")

    # ----- Advanced SMC -----
    try:
        from core.advanced_smc import analyze_smc_v3

        if rates is not None:
            rates_h1 = rates.get("h1")
            rates_m5 = rates.get("m5")
            adv = analyze_smc_v3(rates_h1, rates_m5, signal=signal)
        else:
            adv = {"advanced_score": 0.0, "grade_bonus": 0.0, "patterns": []}

        details["advanced_score"] = float(adv.get("advanced_score", 0) or 0)
        details["patterns"] = list(adv.get("patterns", []) or [])
    except Exception as e:
        print(f"⚠️ SMC V3 advanced layer failed: {e}")

    # ----- Aggregate bonus -----
    grade_bonus = float(details["grade_bonus"])
    adv = float(details["advanced_score"])

    bonus = grade_bonus
    if adv >= 5.0:
        bonus += SMC_V3_ADV_BONUS_MIN
    if any("PD_ZONE" in str(p) for p in details["patterns"]):
        bonus += SMC_V3_PD_ALIGN_BONUS
    if any(
        ("BREAKER" in str(p) or "MITIGATION" in str(p) or "FVG" in str(p))
        for p in details["patterns"]
    ):
        bonus += SMC_V3_ADV_PATTERN_BONUS

    details["smc_v3_bonus"] = round(
        max(min(bonus, SMC_V3_BONUS_CAP), SMC_V3_BONUS_FLOOR),
        2,
    )

    return details


def apply_smc_v3_to_composite(base_composite: float, smc_v3: Dict[str, Any]) -> float:
    """
    يحقن SMC_V3 كـ soft modifier — لا يكسر حدود Composite.
    """
    bonus = float(smc_v3.get("smc_v3_bonus", 0))
    weight = float(smc_v3.get("weight", SMC_V3_WEIGHT))
    return round(float(base_composite) + bonus * weight, 2)


__all__ = [
    "compute_smc_v3_layer",
    "apply_smc_v3_to_composite",
    "SMC_V3_WEIGHT",
    "SMC_V3_BONUS_CAP",
    "SMC_V3_BONUS_FLOOR",
]
