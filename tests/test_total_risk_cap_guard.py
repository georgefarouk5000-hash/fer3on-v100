"""
[FER3ON-FIX-2026-08-27] Tests for the TOTAL_RISK_CAP guard added to
core/risk_manager.py::calculate_smart_lot().

القصة الحقيقية اللي بيغطيها الملف ده: صفقة SMC/LONDON يوم 24/8 فتحت بـ
lot=0.02 (ضعف الـ0.01 المعتاد) على نفس مسافة وقف ~$30 المعتادة — implied
risk فعلي ~$60، خسارة حقيقية $59.84. MIN_LOT_RISK_GUARD الموجودة قبل كده
ماكانتش تمسك الحالة دي لأنها بتتفعّل بس لو lot == MIN_LOT بالظبط.

نفس الـfixtures والـmocking pattern المستخدم في
tests/test_real_risk_percent_clears_guard.py بالحرف (tick_value=1.0,
point=0.01) عشان implied_risk يتحسب بنفس الوحدات المتحقق منها هناك.
"""
from unittest.mock import MagicMock, patch

import core.risk_manager as rm
from core.settings import MAX_SL_DISTANCE_DOLLARS


def _make_fake_sym_info():
    info = MagicMock()
    info.trade_tick_value = 1.0
    info.volume_step = 0.01
    info.point = 0.01
    return info


def _call_smart_lot(**overrides):
    fake_sym_info = _make_fake_sym_info()
    kwargs = dict(
        balance=1000.0, risk_percent=0.75, sl_dist=30.0, symbol="XAUUSD",
        quality_score=75, session="LONDON", exec_grade="A",
    )
    kwargs.update(overrides)
    with patch.object(rm, "mt5") as fake_mt5:
        fake_mt5.symbol_info.return_value = fake_sym_info
        with patch.object(
            rm, "get_loss_limits_status",
            return_value={"daily_used": 0, "daily_limit": 999,
                          "weekly_used": 0, "weekly_limit": 999},
        ):
            with patch.object(rm, "cooldown_active", return_value=False):
                return rm.calculate_smart_lot(**kwargs)


def test_normal_min_lot_trade_is_unaffected():
    """صفقة عادية بـMIN_LOT وسقف وقف $30 قياسي — implied risk تساوي السقف
    بالظبط، ملهاش داعي يتقص."""
    lot, raw_lot, adjustments = _call_smart_lot(
        balance=1000.0, risk_percent=0.75, sl_dist=30.0,
    )
    assert lot > 0
    assert not any('TOTAL_RISK_CAP' in a for a in adjustments), (
        f"a normal MIN_LOT trade at the standard $30 stop must not be "
        f"touched by the new guard: {adjustments}"
    )


def test_boosted_lot_beyond_min_lot_gets_capped_to_budget():
    """اختبار مباشر لحد الـclamp: لو الـraw_lot (قبل التقريب) وصل لمنطقة
    0.02 على مسافة وقف $30 — سواء عبر ضربات مضاعفة مستقبلية أو سقف
    MAX_RISK_TOTAL أعلى مما هو مضبوط دلوقتي — لازم implied risk يترد
    تحت السقف. بنعمل patch مؤقت لـMAX_RISK_TOTAL هنا فقط عشان نضمن نوصل
    فعليًا لمنطقة الـ0.02 ونختبر منطق الـclamp نفسه بمعزل عن قيمة السقف
    الحالية (اللي طلعت أضيق من كفاية لإعادة إنتاج الحادثة الفعلية —
    ده بحد ذاته ملحوظة إيجابية منفصلة، مش جزء من الاختبار)."""
    with patch.object(rm, 'MAX_RISK_TOTAL', 7.0):
        lot, raw_lot, adjustments = _call_smart_lot(
            balance=1000.0, risk_percent=6.5, sl_dist=30.0,
            quality_score=95, exec_grade='ELITE', market_regime='TRENDING',
        )
    assert raw_lot >= 0.015, (
        f"test setup sanity check: raw_lot should reach the 0.02-rounding "
        f"region before clamping, got {raw_lot}"
    )
    assert lot == 0.01, (
        f"a lot inflated past MIN_LOT with the same $30 stop must be "
        f"capped back down to respect MAX_SL_DISTANCE_DOLLARS, got lot={lot} "
        f"adjustments={adjustments}"
    )
    assert any('TOTAL_RISK_CAP' in a for a in adjustments)


def test_capped_lot_never_produces_implied_risk_above_the_dollar_cap():
    """اختبار عام: مهما كان risk_percent، implied_risk النهائي (lot × مسافة
    الوقف بالدولار) ميتخطاش MAX_SL_DISTANCE_DOLLARS — لا بالضبط ولا شوية.
    sl_dist المُمرَّر أكبر من الحد عمدًا (40) عشان نتأكد إن الدالة بتقص
    المسافة نفسها لـMAX_SL_DISTANCE_DOLLARS برضو، مش بس تعتمد على قيمة
    ثابتة مطابقة له بالصدفة."""
    for risk_percent in (1.0, 2.5, 5.0, 8.0, 12.0):
        lot, raw_lot, adjustments = _call_smart_lot(
            balance=1000.0, risk_percent=risk_percent, sl_dist=40.0,
        )
        if lot <= 0:
            continue  # رُفضت الصفقة بالكامل عبر MIN_LOT_RISK_GUARD — مقبول
        implied_risk = lot * (MAX_SL_DISTANCE_DOLLARS / 0.01) * 1.0  # sl_points * tick_value
        assert implied_risk <= MAX_SL_DISTANCE_DOLLARS + 1e-6, (
            f"risk_percent={risk_percent}% produced lot={lot} with implied "
            f"risk ${implied_risk:.2f} > cap ${MAX_SL_DISTANCE_DOLLARS}"
        )


def test_min_lot_still_too_risky_case_falls_through_to_existing_guard():
    """لو حتى MIN_LOT implied risk فوق سقف MIN_LOT_RISK_MULTIPLE_CAP القديم
    (8x)، الحماية القديمة لازم لسه ترفض الصفقة بالكامل (lot=0.0) — التعديل
    الجديد ميغيّرش السلوك ده."""
    lot, raw_lot, adjustments = _call_smart_lot(
        balance=50.0, risk_percent=0.1, sl_dist=30.0,
    )
    assert lot == 0.0, (
        f"a tiny-balance account where even MIN_LOT wildly overshoots the "
        f"intended risk must still be skipped entirely, got lot={lot} "
        f"adjustments={adjustments}"
    )
    assert any('MIN_LOT_RISK_GUARD' in a for a in adjustments)
