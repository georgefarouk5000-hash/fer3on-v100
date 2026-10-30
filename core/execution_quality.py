# =========================================
# FER3ON V5 — EXECUTION QUALITY ENGINE
# المرحلة 6: تقييم جودة التنفيذ قبل الدخول
# SL Distance | RR | Spread | ATR → A+ / A / B / C
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE


# =========================================
# THRESHOLDS
# =========================================

# RR
RR_EXCELLENT   = 3.0
RR_GOOD        = 2.0
RR_ACCEPTABLE  = 1.5

# Spread (نسبة من ATR)
SPREAD_EXCELLENT = 0.05   # < 5% من ATR
SPREAD_GOOD      = 0.10   # < 10%
SPREAD_BAD       = 0.20   # > 20% → رفض

# SL Distance (نسبة من ATR)
SL_MIN_ATR_MULT  = 0.6    # SL أقل من 60% ATR → صغير جداً
SL_MAX_ATR_MULT  = 3.0    # SL أكبر من 300% ATR → كبير جداً

# Risk Multipliers per Grade
GRADE_RISK_MULT = {
    "A+": 1.25,
    "A":  1.00,
    "B":  0.75,
    "C":  0.50,
    "REJECT": 0.0
}


# =========================================
# EVALUATE EXECUTION QUALITY
# =========================================

def evaluate_execution_quality(symbol, sl_dist, tp_dist, atr):
    """
    يُقيّم جودة التنفيذ قبل إرسال الأوردر.

    يُعيد:
      grade       : A+ | A | B | C | REJECT
      risk_mult   : معامل تعديل المخاطرة
      rr_ratio    : نسبة TP/SL
      spread_pct  : نسبة الفارق من ATR
      sl_atr_pct  : نسبة SL من ATR
      reason      : سبب التقييم
      details     : dict مفصّل
    """
    if atr <= 0:
        return _grade("C", "ATR_ZERO", sl_dist, tp_dist, 0, 0, 0)

    tick = mt5.symbol_info_tick(symbol)
    spread = 0.0
    if tick:
        spread = tick.ask - tick.bid

    # --- نسب مهمة ---
    rr_ratio   = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0
    spread_pct = round(spread / atr, 4)       if atr > 0    else 1
    sl_atr_pct = round(sl_dist / atr, 2)      if atr > 0    else 0

    score = 0

    # ======================================
    # 1. R:R RATIO (0-40)
    # ======================================
    if rr_ratio >= RR_EXCELLENT:
        score += 40
        rr_note = "EXCELLENT"
    elif rr_ratio >= RR_GOOD:
        score += 28
        rr_note = "GOOD"
    elif rr_ratio >= RR_ACCEPTABLE:
        score += 16
        rr_note = "ACCEPTABLE"
    else:
        # R:R أقل من 1.5 → REJECT فوري
        return _grade("REJECT", f"RR_TOO_LOW:{rr_ratio}", sl_dist, tp_dist, rr_ratio, spread_pct, sl_atr_pct)

    # ======================================
    # 2. SPREAD (0-30)
    # ======================================
    if spread_pct <= SPREAD_EXCELLENT:
        score += 30
        spread_note = "TIGHT"
    elif spread_pct <= SPREAD_GOOD:
        score += 20
        spread_note = "NORMAL"
    elif spread_pct <= SPREAD_BAD:
        score += 8
        spread_note = "WIDE"
    else:
        return _grade("REJECT", f"SPREAD_TOO_WIDE:{spread_pct:.2%}", sl_dist, tp_dist, rr_ratio, spread_pct, sl_atr_pct)

    # ======================================
    # 3. SL DISTANCE vs ATR (0-30)
    # ======================================
    if sl_atr_pct < SL_MIN_ATR_MULT:
        score += 8
        sl_note = "TOO_TIGHT"
    elif sl_atr_pct > SL_MAX_ATR_MULT:
        score += 8
        sl_note = "TOO_WIDE"
    elif 0.8 <= sl_atr_pct <= 1.8:
        score += 30
        sl_note = "OPTIMAL"
    else:
        score += 18
        sl_note = "ACCEPTABLE"

    # ======================================
    # GRADE FROM SCORE
    # ======================================
    if score >= 90:
        grade = "A+"
    elif score >= 70:
        grade = "A"
    elif score >= 50:
        grade = "B"
    else:
        grade = "C"

    reason = f"RR:{rr_note} | Spread:{spread_note} | SL:{sl_note}"

    print(
        f"⚡ EXEC QUALITY: {grade}"
        f" | RR:{rr_ratio}"
        f" | Spread:{spread_pct:.1%}"
        f" | SL/ATR:{sl_atr_pct}"
        f" | Score:{score}"
    )

    return _grade(grade, reason, sl_dist, tp_dist, rr_ratio, spread_pct, sl_atr_pct)


# =========================================
# HELPER
# =========================================

def _grade(grade, reason, sl_dist, tp_dist, rr, spread_pct, sl_atr_pct):
    return {
        "grade":      grade,
        "risk_mult":  GRADE_RISK_MULT.get(grade, 0.5),
        "rr_ratio":   rr,
        "spread_pct": spread_pct,
        "sl_atr_pct": sl_atr_pct,
        "reason":     reason,
        "sl_dist":    sl_dist,
        "tp_dist":    tp_dist,
        "approved":   grade != "REJECT"
    }
