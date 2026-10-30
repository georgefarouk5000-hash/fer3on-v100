from core.mt5_compat import mt5, MT5_AVAILABLE

from core.candle_patterns import (
    detect_candle_pattern
)


# =========================================
# EMA
# =========================================

def calculate_ema(prices, period):

    multiplier = 2 / (period + 1)

    ema = prices[0]

    for price in prices[1:]:

        ema = (
            (price - ema)
            * multiplier
            + ema
        )

    return ema


# =========================================
# DAILY TREND
# =========================================

def daily_trend(symbol):

    rates = mt5.copy_rates_from_pos(

        symbol,

        mt5.TIMEFRAME_D1,

        0,

        100

    )

    if rates is None:

        return "NONE"

    closes = [

        candle['close']

        for candle in rates

    ]

    ema_fast = calculate_ema(

        closes[-20:],

        20

    )

    ema_slow = calculate_ema(

        closes[-50:],

        50

    )

    if ema_fast > ema_slow:

        return "BUY"

    elif ema_fast < ema_slow:

        return "SELL"

    return "NONE"


# =========================================
# H4 CONFIRMATION
# =========================================

def h4_confirmation(symbol):

    rates = mt5.copy_rates_from_pos(

        symbol,

        mt5.TIMEFRAME_H4,

        0,

        100

    )

    if rates is None:

        return "NONE"

    pattern = detect_candle_pattern(
        rates
    )

    return pattern


# =========================================
# DAILY MACRO SIGNAL
# =========================================

def get_daily_macro_signal(symbol):

    daily_bias = daily_trend(symbol)

    h4_signal = h4_confirmation(symbol)

    print(
        f"🌍 DAILY BIAS: {daily_bias}"
    )

    print(
        f"📊 H4 SIGNAL: {h4_signal}"
    )

    # =========================================
    # BUY
    # =========================================

    if (

        daily_bias == "BUY"

        and h4_signal == "BUY"

    ):

        print(
            "🚀 DAILY MACRO BUY"
        )

        return "BUY"

    # =========================================
    # SELL
    # =========================================

    elif (

        daily_bias == "SELL"

        and h4_signal == "SELL"

    ):

        print(
            "🚀 DAILY MACRO SELL"
        )

        return "SELL"

    return "NONE"