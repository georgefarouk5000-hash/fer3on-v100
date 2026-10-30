# =============================================================================
# FER3ON V9 — SHADOW READINESS BRIDGE
# =============================================================================
# الفلسفة:
#   core/phase3/final_brain.py يحسب "جاهزية الترقية من Shadow إلى Live"
#   (readiness_score 0-100) بناءً على دورات Shadow الفعلية + دقة الموافقة +
#   معدل الرفض الخاطئ. كل موديولات core/phase3/ محصَّنة بـ assert صريح يمنع
#   أي تأثير حي مباشر منها (مثال: core/phase3/final_brain.py سطر 50:
#   `assert not FINAL_BRAIN_LIVE_AUTHORITY`) — حارس أمان متعمَّد بقوة، لا
#   يُلمَس هنا أبدًا.
#
#   هذا الموديول طبقة قراءة خارجية بالكامل: يستهلك فقط get_readiness_report()
#   (دالة قراءة علنية، لا تكتب لأي state) ويُترجم النتيجة إلى تأثير تدريجي
#   صغير جدًا على اللوت — بنفس نمط V6 (Quant Engine) و V7 (Velocity/Regime
#   Fit): bonus/penalty محدود بسقف صريح مطلق، لا حظر أبدًا، fail-safe كامل.
#
#   لماذا تدريجي لا ثنائي (live_ready=True/False فقط):
#   الحالة الفعلية الآن (readiness_score≈61, false_reject_rate≈34%) ليست
#   "جاهزة" لكنها ليست "صفر معلومات" أيضًا. منحها تأثيرًا صفريًا تامًا حتى
#   عتبة 80 يهدر إشارة حقيقية ضعيفة الثقة؛ منحها تأثيرًا كاملًا متهور بصراحة
#   (الكود نفسه يقول false_reject أعلى بـ3.4× من الحد المسموح). الحل: تأثير
#   يتدرج خطيًا مع readiness_score نفسه، وسقف مطلق منخفض حتى عند الجاهزية
#   الكاملة (100) — هامش حذر بشري دائم، لا تأثير "كامل" حتى في أفضل الحالات.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict

from core.settings import (
    V9_READINESS_BRIDGE_ENABLED,
    V9_READINESS_MIN_SCORE_FOR_ANY_EFFECT,
    V9_READINESS_MAX_LOT_EFFECT,
)


def _safe_get_final_brain_readiness() -> Dict[str, Any]:
    """قراءة فقط — لا تأثير، لا كتابة. fail-safe كامل عند أي خطأ."""
    try:
        from core.phase3.final_brain import get_readiness_report
        return get_readiness_report()
    except Exception as exc:
        print(f'⚠️ V9_READINESS_BRIDGE | تعذّرت قراءة final_brain readiness (non-fatal): {exc}')
        return {}


def compute_v9_lot_multiplier() -> Dict[str, Any]:
    """
    يُرجع معامل لوت تدريجي مبني على جاهزية FINAL_BRAIN (Shadow)، بدون لمس
    أي ملف داخل core/phase3/. لا حظر أبدًا — القيمة الدنيا المطلقة محسوبة
    صريحًا، والقيمة العليا محدودة بسقف صريح حتى عند الجاهزية الكاملة.

    Returns
    -------
    dict: {enabled, readiness_score, lot_multiplier, reason}
    """
    if not V9_READINESS_BRIDGE_ENABLED:
        return {"enabled": False, "readiness_score": 0.0, "lot_multiplier": 1.0,
                "reason": "V9_BRIDGE_DISABLED"}

    report = _safe_get_final_brain_readiness()
    if not report:
        return {"enabled": True, "readiness_score": 0.0, "lot_multiplier": 1.0,
                "reason": "NO_READINESS_DATA_NEUTRAL_DEFAULT"}

    readiness_score = float(report.get("readiness_score", 0.0) or 0.0)

    # تحت العتبة الدنيا للأثر: لا توجد ثقة كافية حتى لتأثير صغير — محايد تمامًا
    if readiness_score < V9_READINESS_MIN_SCORE_FOR_ANY_EFFECT:
        return {
            "enabled": True, "readiness_score": readiness_score, "lot_multiplier": 1.0,
            "reason": f"BELOW_MIN_EFFECT_THRESHOLD_{V9_READINESS_MIN_SCORE_FOR_ANY_EFFECT}",
        }

    # تدرّج خطي بين العتبة الدنيا و100 -> [1.0, 1.0 + V9_READINESS_MAX_LOT_EFFECT]
    progress = (readiness_score - V9_READINESS_MIN_SCORE_FOR_ANY_EFFECT) / max(
        1e-6, (100.0 - V9_READINESS_MIN_SCORE_FOR_ANY_EFFECT)
    )
    progress = max(0.0, min(1.0, progress))
    lot_multiplier = 1.0 + (progress * V9_READINESS_MAX_LOT_EFFECT)

    log_line = (
        f"🧠 V9_READINESS_BRIDGE | final_brain_readiness={readiness_score:.1f}"
        f" (live_ready={report.get('live_ready')})"
        f" | progress={progress:.2f} → lot_multiplier=×{lot_multiplier:.3f}"
        f" (سقف مطلق: ×{1.0 + V9_READINESS_MAX_LOT_EFFECT:.2f})"
    )
    print(log_line)

    return {
        "enabled": True,
        "readiness_score": readiness_score,
        "lot_multiplier": round(lot_multiplier, 4),
        "reason": f"GRADUAL_EFFECT_AT_{readiness_score:.1f}",
        "live_ready_per_final_brain": report.get("live_ready", False),
    }
