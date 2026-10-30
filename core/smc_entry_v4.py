# =========================================
# FER3ON-AI-V3 — SMC ENTRY V4 (Wrapper Layer)
# =========================================
# هذا الملف مُنقول بالكامل ومنقول من:
#   core/smc_entry_engine.py  (V2.2 OPERATIONAL)
#
# يُصدّر نفس الواجهة العامة كمحرك V4:
#   - check_smc_entry_sequence(symbol, signal)
#   - get_entry_grade_score(grade)
#   - get_entry_grade_bonus(grade)
#   - should_allow_smc_entry(confirmed, grade)
#
# الهدف: توفير entry-point ثابت اسمه smc_entry_v4
#        يمكن لطبقات Composite وmain الرجوع إليه دون تعديل
#        الكود الأساسي لـ smc_entry_engine (آمن بـ backward-compatible).
# =========================================

from core.smc_entry_engine import (
    check_smc_entry_sequence,
    get_entry_grade_score,
    get_entry_grade_bonus,
    should_allow_smc_entry,
    _grade_smc,
    _inside_zone,
)


# =========================================
# V3 EXTENSION — تُعيد تفسير grade + تُرجع SMC_V3_BONUS
# هذه الزيادة الوحيدة فوق المحرك الأصلي.
# =========================================

V3_GRADE_BONUS = {
    "A+": 5.0,
    "A":  4.0,
    "B+": 2.5,
    "B":  1.5,
    "C":  0.5,
    "NONE": 0.0,
}


def get_v3_grade_bonus(grade: str) -> float:
    return float(V3_GRADE_BONUS.get(str(grade or "NONE").upper(), 0.0))


__all__ = [
    "check_smc_entry_sequence",
    "get_entry_grade_score",
    "get_entry_grade_bonus",
    "should_allow_smc_entry",
    "get_v3_grade_bonus",
]
