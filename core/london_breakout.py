# =========================================
# FER3ON V4 — LONDON BREAKOUT ENGINE
# Asian Range → London Breakout على H1
# UTC time — fixed
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone

from core.utils        import calculate_ema
from core.daily.signal import get_daily_bias
from core.settings     import LONDON_START, LONDON_END


# =========================================
# LONDON SESSION CHECK
# =========================================

def is_london_session():
    hour = datetime.now(timezone.utc).hour
    return LONDON_START <= hour < LONDON_END


# =========================================
# ASIAN RANGE — من بيانات H1 اليوم
# =========================================

def get_asian_range(symbol):
    """
    يحسب نطاق الجلسة الآسيوية (00:00–07:00 UTC)
    من شمعات H1 اليوم
    """
    rates = mt5.copy_rates_from_pos(
        symbol, mt5.TIMEFRAME_H1, 0, 24
    )
    if rates is None or len(rates) < 5:
        return None, None

    now_utc       = datetime.now(timezone.utc)
    midnight_ts   = now_utc.replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    asia_end_ts   = now_utc.replace(
        hour=LONDON_START, minute=0, second=0, microsecond=0
    ).timestamp()

    asian_candles = [
        c for c in rates
        if midnight_ts <= c['time'] < asia_end_ts
    ]

    # Fallback: أول 6 شمعات H1
    if len(asian_candles) < 3:
        asian_candles = list(rates[:7])

    if not asian_candles:
        return None, None

    asian_high = max(c['high'] for c in asian_candles)
    asian_low  = min(c['low']  for c in asian_candles)

    return asian_high, asian_low


# =========================================
# LONDON BREAKOUT SIGNAL
# =========================================

def get_london_breakout_signal(symbol):
    """
    يُفعَّل فقط في جلسة لندن (07:00–12:00 UTC)
    يكسر نطاق الآسيوية + يؤكد بـ EMA + Daily Bias
    """

    if not is_london_session():
        return "NONE"

    # ———————————————
    # Asian Range
    # ———————————————
    asian_high, asian_low = get_asian_range(symbol)
    if asian_high is None:
        return "NONE"

    # ———————————————
    # H1 rates — للتأكيد
    # ———————————————
    rates = mt5.copy_rates_from_pos(
        symbol, mt5.TIMEFRAME_H1, 0, 30
    )
    if rates is None or len(rates) < 20:
        return "NONE"

    closes    = [c['close'] for c in rates]
    last      = rates[-1]
    ema_fast  = calculate_ema(closes, 9)
    ema_slow  = calculate_ema(closes, 21)
    ema_trend = "BUY" if ema_fast > ema_slow else "SELL"

    daily_bias = get_daily_bias(symbol)

    range_size = asian_high - asian_low
    current    = last['close']

    print(
        f"🌅 LONDON | Asian[{asian_low:.1f}–{asian_high:.1f}]"
        f" Price:{current:.1f}"
        f" EMA:{ema_trend}"
        f" Bias:{daily_bias}"
    )

    # ———————————————
    # BREAKOUT UP
    # ———————————————
    if (
        current > asian_high
        and ema_trend == "BUY"
        and (daily_bias == "BUY" or daily_bias == "NONE")
        and range_size > 0
    ):
        print("🚀 LONDON BREAKOUT: BUY")
        return "BUY"

    # ———————————————
    # BREAKOUT DOWN
    # ———————————————
    if (
        current < asian_low
        and ema_trend == "SELL"
        and (daily_bias == "SELL" or daily_bias == "NONE")
        and range_size > 0
    ):
        print("🚀 LONDON BREAKOUT: SELL")
        return "SELL"

    return "NONE"
