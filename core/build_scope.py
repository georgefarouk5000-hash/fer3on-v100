"""
[FER3ON-FIX-2026-08-19 BRAIN-SCOPE] Build-Scoped Learning Filter
=================================================================
امتداد لنمط core/expected_edge_gate.py (فلترة بـ build_id + fallback محافظ)
لكن لـ"عقل" القرار الحي: history_learner / trade_dna / confidence_engine /
self_optimizer / adaptive_weighting.

المشكلة قبل هذا الملف:
  الحماية بالـ BUILD_ID كانت واصلة للتقييم (certification/analytics) ولبوابة
  الدخول (expected_edge_gate) فقط، بينما 65% من master_score (dna 35% +
  history 30%) ومحركات تعديل الأوزان كانت تقرأ كل صفقات كل النسخ مخلوطة —
  بما فيها صفقات النسخة الفاشلة التي شخصّها تقرير 2026-08-19.

القاعدة هنا:
  - صفقة "من البيلد الحالي" = build_id == BUILD_ID، أو (لو مفيش build_id)
    timestamp >= BUILD_DEPLOYED_AT.
  - أي صف غير كده (LEGACY_* / SYNTHETIC_BOOTSTRAP / قديم) لا يدخل في أي
    حساب تعلّم حي. يفضل موجودًا على الديسك كأرشيف — لا مسح للبيانات.
  - لو مفيش BUILD_ID/BUILD_DEPLOYED_AT أصلًا (بيئة قديمة) لا نستبعد شيئًا
    (سلوك قديم، لا كسر للتوافق).
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from core.settings import BUILD_ID as _BUILD_ID
    from core.settings import BUILD_DEPLOYED_AT as _DEPLOYED_AT
except Exception:  # pragma: no cover - بيئة بدون settings
    _BUILD_ID = None
    _DEPLOYED_AT = None

try:
    from core.account_scope import get_cached_account_id as _get_current_account_id
except Exception:  # pragma: no cover - بيئة بدون account_scope
    def _get_current_account_id():
        return ""

LEGACY_LABELS = {"LEGACY_PRE_BUILD1", "SYNTHETIC_BOOTSTRAP"}

# حد أدنى للعينة قبل الوثوق بإحصائية متعلمة من البيلد الحالي —
# نفس فلسفة MIN_SAMPLE_TRADES في expected_edge_gate (هناك 50 للبوابة،
# هنا 5 فقط لأنها درجات تعلّم داخلية وليست قرار سماح/رفض نهائي).
MIN_LEARNING_SAMPLE = 5


def _cutoff():
    if not _DEPLOYED_AT:
        return None
    try:
        dt = datetime.fromisoformat(str(_DEPLOYED_AT).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _is_current_build(row, date_field):
    """الفحص الأصلي بالحرف (build_id أو fallback بالتاريخ) — بدون أي علاقة
    بالحساب. مفصول في دالة مستقلة عشان is_current_build_row تقدر تضيف فحص
    الحساب فوقه من غير ما تكرر أو تكسر أي مسار من المسارات الموجودة."""
    build_id = str(row.get("build_id", "") or "").strip()
    if build_id:
        return bool(_BUILD_ID) and build_id == str(_BUILD_ID)

    cutoff = _cutoff()
    if cutoff is None:
        # لا يوجد BUILD_ID/BUILD_DEPLOYED_AT في البيئة — لا نستبعد شيئًا
        return True

    raw = row.get(date_field, "") or row.get("timestamp", "") or ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    return dt >= cutoff


def _is_current_account(row):
    """
    [FER3ON-FIX-2026-08-28] فحص إضافي مستقل عن فحص البيلد. المشكلة اللي
    ده بيحلها: تغيير حساب MT5 من غير ما البيلد يتغيّر (نفس الكود، حساب
    ديمو تاني) — build_id بتاع صفوف الحساب القديم بيفضل يطابق البيلد
    الحالي بالظبط، فمفيش فلترة تستبعدهم غير دي.

    نفس فلسفة فحص build_id بالحرف: لو الصف مالوش account_id خالص (بيانات
    قديمة اتسجلت قبل الإضافة دي) لا نستبعد حاجة — تراجع (backward compat)
    مش كسر. الاستبعاد بيحصل بس لو الصف *فيه* account_id صريح ومختلف عن
    الحساب الحالي.
    """
    account_id = str(row.get("account_id", "") or "").strip()
    if not account_id:
        return True
    current = _get_current_account_id()
    return bool(current) and account_id == str(current)


def is_current_build_row(row, date_field="date"):
    """True لو الصف أنتجه البيلد الحالي *وعلى الحساب الحالي* (أو لو مفيش
    سياق بيلد/حساب أصلًا)."""
    if not isinstance(row, dict):
        return False
    return _is_current_build(row, date_field) and _is_current_account(row)


def filter_current_build_rows(rows, date_field="date"):
    """يرجع فقط صفوف البيلد الحالي من قائمة صفوف (dicts)."""
    return [r for r in (rows or []) if is_current_build_row(r, date_field=date_field)]
