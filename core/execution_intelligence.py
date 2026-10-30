# =========================================
# FER3ON V5.1 — EXECUTION INTELLIGENCE
# Priority #3: ذكاء التنفيذ الكامل
# Spread + ATR + RR + Distance-To-Liquidity
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone


# =========================================
# THRESHOLDS المحدثة
# =========================================

# RR
RR_ELITE      = 3.5
RR_EXCELLENT  = 2.5
RR_GOOD       = 2.0
RR_ACCEPTABLE = 1.5
RR_MINIMUM    = 1.2

# Spread كنسبة من ATR
SPREAD_ELITE     = 0.03   # < 3%
SPREAD_EXCELLENT = 0.06   # < 6%
SPREAD_GOOD      = 0.10   # < 10%
SPREAD_WIDE      = 0.18   # < 18%
SPREAD_REJECT    = 0.25   # > 25% → REJECT

# ATR Health
ATR_MINIMUM_GOLD = 1.5    # أقل حد للـ ATR على الذهب (نقطة)

# Lot Size Bounds
LOT_MIN  = 0.01
LOT_MAX_CONSERVATIVE  = 0.50   # للحسابات الصغيرة
LOT_MAX_NORMAL        = 5.00

# Session Quality Multipliers
SESSION_MULT = {
    "LONDON":    1.20,
    "NEWYORK":   1.20,
    "OVERLAP":   1.30,   # London/NY overlap — أفضل وقت
    "ASIA":      0.80,
    "OFF_HOURS": 0.60,
}

# Grade→Risk Multiplier
EXEC_GRADE_MULT = {
    "ELITE":  1.40,
    "A+":     1.25,
    "A":      1.00,
    "B":      0.75,
    "C":      0.50,
    "REJECT": 0.00
}


# =========================================
# SMART LOT SIZE CALCULATOR
# =========================================

def calculate_smart_lot(
    balance,
    risk_percent,
    sl_dist,
    symbol="XAUUSD",
    quality_score=70,
    session="UNKNOWN",
    recovery_mode=False
):
    """
    حساب حجم اللوت الذكي مع مراعاة:
      - الرصيد والمخاطرة
      - جودة الصفقة
      - الجلسة
      - وضع الاسترداد

    يُعيد:
      lot        : الحجم النهائي
      raw_lot    : الحجم الخام قبل التعديلات
      adjustments: قائمة التعديلات المطبقة
    """
    if sl_dist <= 0 or balance <= 0:
        return LOT_MIN, LOT_MIN, ["ERROR: Invalid inputs"]

    # حجم نقطة الذهب
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        tick_value = 0.10   # قيمة افتراضية للذهب
        lot_step   = 0.01
    else:
        tick_value = symbol_info.trade_tick_value
        lot_step   = symbol_info.volume_step

    # الحجم الخام
    if tick_value > 0:
        risk_amount = balance * (risk_percent / 100)
        raw_lot     = risk_amount / (sl_dist * tick_value)
    else:
        raw_lot = LOT_MIN

    adjustments = []
    lot = raw_lot

    # تعديل بناءً على جودة الصفقة
    if quality_score >= 90:
        lot *= 1.20
        adjustments.append(f"Quality90+: x1.20")
    elif quality_score >= 80:
        lot *= 1.10
        adjustments.append(f"Quality80+: x1.10")
    elif quality_score < 60:
        lot *= 0.75
        adjustments.append(f"Quality<60: x0.75")

    # تعديل بناءً على الجلسة
    sess_mult = SESSION_MULT.get(session, 1.0)
    if sess_mult != 1.0:
        lot *= sess_mult
        adjustments.append(f"Session({session}): x{sess_mult}")

    # وضع الاسترداد — تقليص حاد
    if recovery_mode:
        lot *= 0.50
        adjustments.append("RecoveryMode: x0.50")

    # تقريب لـ lot_step
    if lot_step > 0:
        lot = round(lot / lot_step) * lot_step

    # حدود الحماية
    max_lot = LOT_MAX_CONSERVATIVE if balance < 1000 else LOT_MAX_NORMAL
    lot = max(LOT_MIN, min(lot, max_lot))
    lot = round(lot, 2)

    return lot, round(raw_lot, 2), adjustments


# =========================================
# SMART ENTRY TIMING
# =========================================

def check_entry_timing(symbol, signal):
    """
    يتحقق من توقيت الدخول المثالي:
      - هل السعر في منطقة FVG أو OB؟
      - هل الشمعة تؤكد الاتجاه؟
      - هل الـ spread مناسب الآن؟

    يُعيد:
      optimal : bool
      score   : 0-10
      reason  : نص الشرح
    """
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 10)
    tick = mt5.symbol_info_tick(symbol)

    if rates_m5 is None or tick is None:
        return False, 0, "NO_DATA"

    score = 5   # neutral
    reasons = []

    # 1. تحقق من Spread الحالي
    spread = tick.ask - tick.bid
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        spread_pts = spread / symbol_info.point
        if spread_pts <= 3:
            score += 3
            reasons.append("SPREAD_TIGHT")
        elif spread_pts > 8:
            score -= 3
            reasons.append("SPREAD_WIDE")

    # 2. تحقق من اتجاه الشمعة الأخيرة
    last_candle = rates_m5[-1]
    candle_bull = last_candle["close"] > last_candle["open"]
    candle_bear = last_candle["close"] < last_candle["open"]

    if (signal == "BUY" and candle_bull) or (signal == "SELL" and candle_bear):
        score += 2
        reasons.append("CANDLE_ALIGNED")

    # 3. تحقق من موقع السعر نسبةً للنطاق
    high_5 = max(c["high"]  for c in rates_m5)
    low_5  = min(c["low"]   for c in rates_m5)
    range_ = high_5 - low_5
    current = (tick.ask + tick.bid) / 2

    if range_ > 0:
        pos = (current - low_5) / range_
        if signal == "BUY" and pos < 0.35:    # قرب القاع — دخول شراء جيد
            score += 1
            reasons.append("NEAR_LOW")
        elif signal == "SELL" and pos > 0.65:  # قرب القمة — دخول بيع جيد
            score += 1
            reasons.append("NEAR_HIGH")

    optimal = score >= 7
    return optimal, min(score, 10), " | ".join(reasons)


# =========================================
# FULL EXECUTION INTELLIGENCE
# =========================================

def execute_intelligence_check(
    symbol,
    signal,
    sl_dist,
    tp_dist,
    atr,
    liquidity_map=None,
    session="UNKNOWN",
    quality_score=70,
    strategy=None,
    market_regime=None
):
    """
    الفحص الشامل للتنفيذ الذكي.

    يُعيد:
      approved       : bool
      grade          : ELITE | A+ | A | B | C | REJECT
      score          : 0-100
      risk_mult      : معامل تعديل المخاطرة
      rr_ratio       : نسبة المكسب للخسارة
      spread_pct     : نسبة الفارق
      entry_timing   : OPTIMAL | GOOD | NORMAL | POOR
      reason         : سبب القرار
      details        : dict كامل
    """
    # =====================================
    # 1. بيانات السوق
    # =====================================
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if not tick or not symbol_info:
        return _exec_result("REJECT", 0, "NO_MARKET_DATA")

    spread = tick.ask - tick.bid
    spread_pts = spread / symbol_info.point if symbol_info.point > 0 else 0

    # =====================================
    # 2. فحص ATR الأساسي
    # =====================================
    if atr < ATR_MINIMUM_GOLD:
        return _exec_result("REJECT", 0, f"ATR_TOO_LOW:{atr:.2f}")

    if market_regime in {"CRISIS", "UNKNOWN"}:
        return _exec_result("REJECT", 0, f"MARKET_REGIME_UNFAVORABLE:{market_regime}")

    # =====================================
    # 3. حساب النسب
    # =====================================
    rr_ratio   = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0
    spread_pct = round(spread / atr, 4)       if atr > 0    else 1
    sl_atr     = round(sl_dist / atr, 2)      if atr > 0    else 0

    exec_score = 0

    # =====================================
    # 4. RR SCORING (0-40)
    # =====================================
    if rr_ratio >= RR_ELITE:
        exec_score += 40
        rr_note = "ELITE"
    elif rr_ratio >= RR_EXCELLENT:
        exec_score += 33
        rr_note = "EXCELLENT"
    elif rr_ratio >= RR_GOOD:
        exec_score += 26
        rr_note = "GOOD"
    elif rr_ratio >= RR_ACCEPTABLE:
        exec_score += 18
        rr_note = "ACCEPTABLE"
    elif rr_ratio >= RR_MINIMUM:
        exec_score += 10
        rr_note = "MINIMUM"
    else:
        return _exec_result("REJECT", 0, f"RR_TOO_LOW:{rr_ratio}")

    # =====================================
    # 5. SPREAD SCORING (0-25)
    # =====================================
    if spread_pct <= SPREAD_ELITE:
        exec_score += 25
        spread_note = "ELITE_TIGHT"
    elif spread_pct <= SPREAD_EXCELLENT:
        exec_score += 20
        spread_note = "EXCELLENT"
    elif spread_pct <= SPREAD_GOOD:
        exec_score += 14
        spread_note = "GOOD"
    elif spread_pct <= SPREAD_WIDE:
        exec_score += 7
        spread_note = "WIDE"
    elif spread_pct <= SPREAD_REJECT:
        exec_score += 2
        spread_note = "VERY_WIDE"
    else:
        return _exec_result("REJECT", 0, f"SPREAD_TOO_WIDE:{spread_pct:.2%}")

    # =====================================
    # 6. SL DISTANCE vs ATR (0-20)
    # =====================================
    if 0.8 <= sl_atr <= 1.8:
        exec_score += 20
        sl_note = "OPTIMAL"
    elif 0.6 <= sl_atr <= 2.2:
        exec_score += 12
        sl_note = "ACCEPTABLE"
    elif sl_atr < 0.6:
        exec_score += 5
        sl_note = "TOO_TIGHT"
    else:
        exec_score += 4
        sl_note = "TOO_WIDE"

    # =====================================
    # 7. LIQUIDITY MAP BONUS (0-15)
    # =====================================
    liq_bonus = 0
    liq_note  = "NO_MAP"
    if liquidity_map and liquidity_map.get("liquidity_score", 0) >= 5:
        liq_dir   = liquidity_map.get("direction", "NEUTRAL")
        dist_next = liquidity_map.get("distance_next", 0)

        if (signal == "BUY" and liq_dir == "UP") or \
           (signal == "SELL" and liq_dir == "DOWN"):
            if dist_next >= sl_dist * 3:
                liq_bonus = 15
                liq_note  = "MAP_EXCELLENT"
            elif dist_next >= sl_dist * 2:
                liq_bonus = 10
                liq_note  = "MAP_GOOD"
            else:
                liq_bonus = 5
                liq_note  = "MAP_ALIGNED"
        elif liq_dir != "NEUTRAL":
            liq_bonus = -8
            liq_note  = "MAP_CONFLICT"

    exec_score += liq_bonus

    # =====================================
    # 8. ENTRY TIMING (0-15)
    # =====================================
    timing_optimal, timing_score, timing_reason = check_entry_timing(symbol, signal)
    timing_bonus = round(timing_score * 1.5)
    exec_score  += timing_bonus
    entry_timing = "OPTIMAL" if timing_score >= 8 else ("GOOD" if timing_score >= 6 else "NORMAL")
    if not timing_optimal:
        exec_score -= 8

    # =====================================
    # 9. GRADE
    # =====================================
    total_possible = 100
    pct = exec_score / total_possible * 100

    if pct >= 90:
        grade = "ELITE"
    elif pct >= 78:
        grade = "A+"
    elif pct >= 65:
        grade = "A"
    elif pct >= 50:
        grade = "B"
    elif pct >= 35:
        grade = "C"
    else:
        return _exec_result("REJECT", exec_score, f"LOW_EXEC_SCORE:{exec_score}")

    reason = (
        f"RR:{rr_note}({rr_ratio})"
        f" | Spread:{spread_note}({spread_pct:.1%})"
        f" | SL:{sl_note}({sl_atr:.1f}x)"
        f" | Liq:{liq_note}"
        f" | Timing:{entry_timing}"
    )

    print(
        f"⚡ EXEC INTELLIGENCE: {grade}"
        f" | Score:{exec_score}/{total_possible}"
        f" | RR:{rr_ratio}"
        f" | Spread:{spread_pct:.1%}"
        f" | Timing:{entry_timing}"
    )

    return {
        "approved":     True,
        "grade":        grade,
        "score":        exec_score,
        "risk_mult":    EXEC_GRADE_MULT.get(grade, 1.0),
        "rr_ratio":     rr_ratio,
        "spread_pct":   spread_pct,
        "spread_pts":   round(spread_pts, 1),
        "sl_atr":       sl_atr,
        "entry_timing": entry_timing,
        "liq_bonus":    liq_bonus,
        "reason":       reason,
        "sl_dist":      sl_dist,
        "tp_dist":      tp_dist,
        "details": {
            "rr_note":    rr_note,
            "spread_note": spread_note,
            "sl_note":    sl_note,
            "liq_note":   liq_note,
            "timing_reason": timing_reason,
        }
    }


def _exec_result(grade, score, reason):
    return {
        "approved":     grade != "REJECT",
        "grade":        grade,
        "score":        score,
        "risk_mult":    EXEC_GRADE_MULT.get(grade, 0.0),
        "rr_ratio":     0,
        "spread_pct":   0,
        "spread_pts":   0,
        "sl_atr":       0,
        "entry_timing": "POOR",
        "liq_bonus":    0,
        "reason":       reason,
        "sl_dist":      0,
        "tp_dist":      0,
        "details":      {}
    }
