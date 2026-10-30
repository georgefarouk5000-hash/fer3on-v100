# =========================================
# FER3ON V5.6 — EXECUTION OPTIMIZER V2
# Dynamic deviation + filling mode + lot pressure
# =========================================

from datetime import datetime, timezone
from core.mt5_compat import mt5, MT5_AVAILABLE


GRADE_SCORE = {
    "ELITE": 100,
    "A+": 92,
    "A": 84,
    "B+": 76,
    "B": 68,
    "C": 55,
    "REJECT": 20,
}


def _safe_mid_price(tick):
    if not tick:
        return 0.0
    return (float(tick.ask) + float(tick.bid)) / 2.0


def _get_supported_filling(symbol_info, preferred):
    """
    يحاول اختيار filling mode مناسب بدون كسر التوافق.
    في MT5 Python قد تختلف القيم بين الوسطاء، لذلك نحافظ على fallback آمن.
    """
    candidates = []
    if preferred == "RETURN":
        candidates = [
            (getattr(mt5, "ORDER_FILLING_RETURN", None), "RETURN"),
            (getattr(mt5, "ORDER_FILLING_IOC", None), "IOC"),
            (getattr(mt5, "ORDER_FILLING_FOK", None), "FOK"),
        ]
    else:
        candidates = [
            (getattr(mt5, "ORDER_FILLING_IOC", None), "IOC"),
            (getattr(mt5, "ORDER_FILLING_RETURN", None), "RETURN"),
            (getattr(mt5, "ORDER_FILLING_FOK", None), "FOK"),
        ]

    supported = getattr(symbol_info, "filling_mode", None)
    for value, name in candidates:
        if value is None:
            continue
        if supported is None:
            return value, name
        try:
            if supported == value:
                return value, name
        except Exception:
            pass

    for value, name in candidates:
        if value is not None:
            return value, name

    return getattr(mt5, "ORDER_FILLING_IOC", 1), "IOC"


def optimize_order_execution(
    symbol,
    signal,
    exec_quality,
    ml_result,
    session,
    atr,
    rr_ratio,
    tick=None,
    symbol_info=None,
):
    """
    يضبط التنفيذ قبل إرسال الأمر:
      - deviation ديناميكي
      - filling mode مناسب للحالة
      - تقليص اللوت لو execution pressure مرتفع
      - رفض الحالات الشاذة جداً بدل إرسال أمر سيء
    """
    tick = tick or mt5.symbol_info_tick(symbol)
    symbol_info = symbol_info or mt5.symbol_info(symbol)

    if not tick or not symbol_info:
        return {
            "approved": False,
            "reason": "NO_MARKET_DATA",
            "mode": "BLOCKED",
            "score": 0,
            "deviation": 20,
            "filling_type": getattr(mt5, "ORDER_FILLING_IOC", 1),
            "filling_name": "IOC",
            "lot_multiplier": 1.0,
            "comment_tag": "EX2_BLOCK",
            "mid_price": 0.0,
        }

    point = float(getattr(symbol_info, "point", 0.01) or 0.01)
    spread = float(tick.ask - tick.bid)
    spread_pts = round(spread / point, 1) if point > 0 else 0.0
    atr = float(atr or 0)
    atr_pts = atr / point if atr > 0 and point > 0 else 0.0
    spread_atr = (spread / atr) if atr > 0 else 0.0

    exec_grade = str(exec_quality.get("grade", "B") or "B").upper()
    exec_score = float(exec_quality.get("score", GRADE_SCORE.get(exec_grade, 68)) or GRADE_SCORE.get(exec_grade, 68))
    ml_prob = float(ml_result.get("ensemble_prob", 0.5) or 0.5)
    ml_score = float(ml_result.get("ml_score", 50) or 50)

    hour = datetime.now(timezone.utc).hour
    overlap = session == "OVERLAP" or (12 <= hour <= 16)
    premium_session = session in ("LONDON", "NEWYORK", "OVERLAP")

    pressure = 0
    reasons = []

    if spread_pts >= 35 or spread_atr >= 0.22:
        pressure += 5
        reasons.append("SPREAD_SHOCK")
    elif spread_pts >= 20 or spread_atr >= 0.14:
        pressure += 3
        reasons.append("WIDE_SPREAD")
    elif spread_pts >= 10 or spread_atr >= 0.08:
        pressure += 1
        reasons.append("SPREAD_ELEVATED")

    if atr_pts > 0:
        if atr_pts >= 900:
            pressure += 3
            reasons.append("VOL_EXTREME")
        elif atr_pts >= 500:
            pressure += 2
            reasons.append("VOL_HIGH")

    if rr_ratio < 1.5:
        pressure += 3
        reasons.append("RR_WEAK")
    elif rr_ratio < 2.0:
        pressure += 1
        reasons.append("RR_TIGHT")

    if exec_score < 60:
        pressure += 3
        reasons.append("EXEC_WEAK")
    elif exec_score < 75:
        pressure += 1
        reasons.append("EXEC_MID")

    if ml_prob < 0.45 or ml_score < 45:
        pressure += 2
        reasons.append("ML_CAUTIOUS")
    elif ml_prob > 0.70 and exec_score >= 84:
        pressure -= 1
        reasons.append("ML_SUPPORT")

    if not premium_session:
        pressure += 1
        reasons.append("OFF_PEAK")
    if overlap:
        pressure -= 1
        reasons.append("SESSION_DEPTH")

    pressure = max(0, pressure)

    if pressure >= 8 or (spread_pts >= 25 and rr_ratio < 1.8):
        return {
            "approved": False,
            "reason": "EXECUTION_PRESSURE_TOO_HIGH:" + ",".join(reasons[:4]),
            "mode": "BLOCKED",
            "score": max(0, 100 - pressure * 10),
            "deviation": 35,
            "filling_type": getattr(mt5, "ORDER_FILLING_IOC", 1),
            "filling_name": "IOC",
            "lot_multiplier": 0.60,
            "comment_tag": "EX2_BLOCK",
            "mid_price": round(_safe_mid_price(tick), 3),
            "spread_pts": spread_pts,
            "spread_atr": round(spread_atr, 4),
        }

    if pressure <= 1 and exec_score >= 84 and ml_prob >= 0.60 and rr_ratio >= 2.0:
        mode = "PRECISION"
        deviation = 10 if premium_session else 12
        lot_multiplier = 0.95
        preferred_fill = "RETURN"
    elif pressure <= 4:
        mode = "BALANCED"
        deviation = 18 if premium_session else 22
        lot_multiplier = 0.95 if pressure >= 3 else 1.00
        preferred_fill = "IOC"
    else:
        mode = "DEFENSIVE"
        deviation = 26 if premium_session else 30
        lot_multiplier = 0.85
        preferred_fill = "IOC"

    filling_type, filling_name = _get_supported_filling(symbol_info, preferred_fill)

    optimizer_score = round(
        min(
            100,
            max(
                0,
                exec_score * 0.60 +
                (ml_score if ml_result.get("models_trained") else 50) * 0.20 +
                max(0, 100 - spread_pts * 2) * 0.20 -
                pressure * 5
            )
        ),
        1,
    )

    reason = " | ".join(reasons[:5]) if reasons else "ORDER_FLOW_CLEAN"

    return {
        "approved": True,
        "reason": reason,
        "mode": mode,
        "score": optimizer_score,
        "deviation": int(max(8, min(deviation, 40))),
        "filling_type": filling_type,
        "filling_name": filling_name,
        "lot_multiplier": float(lot_multiplier),
        "comment_tag": f"EX2_{mode}",
        "mid_price": round(_safe_mid_price(tick), 3),
        "spread_pts": spread_pts,
        "spread_atr": round(spread_atr, 4),
    }
