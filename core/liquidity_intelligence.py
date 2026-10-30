# =========================================
# FER3ON V5 — LIQUIDITY INTELLIGENCE
# المرحلة 4: رصد السيولة الاحترافي الكامل
# Asian High/Low | London/NY Sweep | Equal H/L
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone


# =========================================
# ASIAN SESSION HIGH/LOW
# الجلسة الآسيوية: 00:00 - 08:00 UTC
# =========================================

def get_asian_range(symbol, *, rates=None):
    """
    يحسب أعلى وأدنى نقطة في الجلسة الآسيوية اليومية.
    يُعيد: {"high": float, "low": float, "valid": bool}
    """
    if rates is None:
        # نحتاج بيانات M15 لآخر 24 ساعة
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 96)
    if rates is None or len(rates) < 10:
        return {"high": 0, "low": 0, "valid": False}

    asian_highs = []
    asian_lows  = []

    for candle in rates:
        candle_time = datetime.fromtimestamp(candle["time"], tz=timezone.utc)
        hour = candle_time.hour
        # الجلسة الآسيوية: 0-7 UTC
        if 0 <= hour < 8:
            asian_highs.append(candle["high"])
            asian_lows.append(candle["low"])

    if len(asian_highs) < 4:
        return {"high": 0, "low": 0, "valid": False}

    return {
        "high":  max(asian_highs),
        "low":   min(asian_lows),
        "valid": True,
        "range": max(asian_highs) - min(asian_lows)
    }


# =========================================
# DETECT SESSION SWEEP
# هل اخترق السعر نطاق الجلسة السابقة؟
# =========================================

def detect_session_sweep(
    symbol,
    *,
    rates_m5=None,
    asian_data=None,
    as_of=None,
):
    """
    يرصد اختراق نطاق الجلسة الآسيوية
    من قِبل لندن أو نيويورك.

    يُعيد:
      "LONDON_SWEEP_HIGH"  | "LONDON_SWEEP_LOW"
      "NY_SWEEP_HIGH"      | "NY_SWEEP_LOW"
      "NONE"
    """
    asian = asian_data if asian_data is not None else get_asian_range(symbol)
    if not asian["valid"]:
        return "NONE", asian

    if as_of is None:
        now_hour = datetime.now(timezone.utc).hour
    else:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        now_hour = as_of.astimezone(timezone.utc).hour

    if rates_m5 is None:
        rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 20)
    if rates_m5 is None:
        return "NONE", asian

    current_high  = max(c["high"]  for c in rates_m5[-5:])
    current_low   = min(c["low"]   for c in rates_m5[-5:])
    current_close = rates_m5[-1]["close"]

    sweep_result = "NONE"

    # لندن: 8-12 UTC
    if 8 <= now_hour < 13:
        if current_high > asian["high"] and current_close < asian["high"]:
            sweep_result = "LONDON_SWEEP_HIGH"
        elif current_low < asian["low"] and current_close > asian["low"]:
            sweep_result = "LONDON_SWEEP_LOW"

    # نيويورك: 13-17 UTC
    elif 13 <= now_hour < 18:
        if current_high > asian["high"] and current_close < asian["high"]:
            sweep_result = "NY_SWEEP_HIGH"
        elif current_low < asian["low"] and current_close > asian["low"]:
            sweep_result = "NY_SWEEP_LOW"

    if sweep_result != "NONE":
        print(f"💧 LIQUIDITY SWEEP DETECTED: {sweep_result}")

    return sweep_result, asian


# =========================================
# EQUAL HIGHS / EQUAL LOWS
# مناطق التجمع — هدف السيولة
# =========================================

def detect_equal_levels(symbol, tolerance_pips=3.0, *, rates_h1=None):
    """
    يرصد Equal Highs و Equal Lows في H1.
    مناطق تتجمع فيها السيولة قبل الاختراق.

    يُعيد:
      {"equal_highs": [price, ...], "equal_lows": [price, ...]}
    """
    rates = rates_h1
    if rates is None:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    if rates is None or len(rates) < 10:
        return {"equal_highs": [], "equal_lows": []}

    highs = [c["high"] for c in rates]
    lows  = [c["low"]  for c in rates]

    equal_highs = _find_equal_levels(highs, tolerance_pips)
    equal_lows  = _find_equal_levels(lows, tolerance_pips)

    if equal_highs:
        print(f"📍 Equal Highs: {equal_highs}")
    if equal_lows:
        print(f"📍 Equal Lows:  {equal_lows}")

    return {"equal_highs": equal_highs, "equal_lows": equal_lows}


def _find_equal_levels(prices, tolerance):
    """يجد الأسعار المتقاربة جداً (مناطق تجمع)"""
    equal_zones = []
    visited = set()

    for i in range(len(prices)):
        if i in visited:
            continue
        cluster = [prices[i]]
        for j in range(i + 1, len(prices)):
            if abs(prices[j] - prices[i]) <= tolerance:
                cluster.append(prices[j])
                visited.add(j)
        if len(cluster) >= 2:
            equal_zones.append(round(float(sum(cluster)) / len(cluster), 2))

    return equal_zones


# =========================================
# LIQUIDITY BIAS — الناتج النهائي
# =========================================

def get_liquidity_bias(
    symbol,
    *,
    rates_m15=None,
    rates_m5=None,
    rates_h1=None,
    current_price=None,
    as_of=None,
):
    """
    يجمع كل مؤشرات السيولة ويُنتج:
      BIAS:  BUY | SELL | NEUTRAL
      score: 0-15 (يُستخدم في Confidence Engine)
      data:  كل التفاصيل

    منطق الـ BIAS:
      - Sweep أسفل القاع ثم صعود → BUY (السيولة أُخذت من الأسفل)
      - Sweep فوق القمة ثم هبوط  → SELL
    """
    asian = get_asian_range(symbol, rates=rates_m15) if rates_m15 is not None else None
    sweep_type, asian = detect_session_sweep(
        symbol,
        rates_m5=rates_m5,
        asian_data=asian,
        as_of=as_of,
    )
    equal_levels = detect_equal_levels(symbol, rates_h1=rates_h1)

    if current_price is None:
        current_price = 0
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            current_price = (tick.ask + tick.bid) / 2

    bias  = "NEUTRAL"
    score = 7   # neutral default

    # Sweep تحت القاع ثم ارتداد → BUY (إشارة صعود)
    if sweep_type in ("LONDON_SWEEP_LOW", "NY_SWEEP_LOW"):
        bias  = "BUY"
        score = 14

    # Sweep فوق القمة ثم ارتداد → SELL (إشارة هبوط)
    elif sweep_type in ("LONDON_SWEEP_HIGH", "NY_SWEEP_HIGH"):
        bias  = "SELL"
        score = 14

    # Equal Lows قريبة → هدف للاتجاه الهابط لسحب السيولة
    elif equal_levels["equal_lows"] and current_price > 0:
        nearest_low = min(
            equal_levels["equal_lows"],
            key=lambda x: abs(x - current_price)
        )
        dist = abs(current_price - nearest_low)
        if dist < 15:   # أقل من 15 نقطة
            bias  = "SELL"
            score = 10

    # Equal Highs قريبة → هدف للاتجاه الصاعد
    elif equal_levels["equal_highs"] and current_price > 0:
        nearest_high = min(
            equal_levels["equal_highs"],
            key=lambda x: abs(x - current_price)
        )
        dist = abs(current_price - nearest_high)
        if dist < 15:
            bias  = "BUY"
            score = 10

    near_zone = (sweep_type != "NONE" or
                 bool(equal_levels["equal_highs"]) or
                 bool(equal_levels["equal_lows"]))

    print(
        f"💧 LIQUIDITY BIAS: {bias}"
        f" | Score:{score}/15"
        f" | Sweep:{sweep_type}"
        f" | AsianH:{asian.get('high', 0):.2f}"
        f" AsianL:{asian.get('low', 0):.2f}"
    )

    return {
        "bias":         bias,
        "score":        score,
        "sweep":        sweep_type,
        "asian_high":   asian.get("high", 0),
        "asian_low":    asian.get("low", 0),
        "equal_highs":  equal_levels["equal_highs"],
        "equal_lows":   equal_levels["equal_lows"],
        "near_zone":    near_zone
    }
