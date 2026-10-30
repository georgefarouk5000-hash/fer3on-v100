from core.mt5_compat import mt5, MT5_AVAILABLE

from core.utils import (
    calculate_ema
)


# =========================================
# TREND DIRECTION
# =========================================

def trend_direction(rates):
    if rates is None or len(rates) < 50:
        return "NONE"

    closes = [

        candle['close']

        for candle in rates

    ]

    # FIX 5: EMA صحيح ✅
    ema_fast = calculate_ema(closes, 20)

    ema_slow = calculate_ema(closes, 50)

    if ema_fast > ema_slow:

        return "BUY"

    elif ema_fast < ema_slow:

        return "SELL"

    return "NONE"


# =========================================
# SIMPLE PRICE ACTION
# =========================================

def candle_signal(rates):
    if rates is None or len(rates) < 1:
        return "NONE"

    last = rates[-1]

    body = abs(

        last['close']

        - last['open']

    )

    candle_range = (
        last['high']
        - last['low']
    )
    if candle_range <= 0:
        return "NONE"

    if (

        last['close'] > last['open']

        and body > candle_range * 0.6

    ):

        return "BUY"

    elif (

        last['close'] < last['open']

        and body > candle_range * 0.6

    ):

        return "SELL"

    return "NONE"


# =========================================
# DAILY SIGNAL
# =========================================

def daily_setup_from_rates(daily_rates, h4_rates):
    """Return aligned D1 trend/H4 candle signals using closed bars only."""
    if daily_rates is None or len(daily_rates) < 51:
        return "NONE", "NONE"
    if h4_rates is None or len(h4_rates) < 2:
        return "NONE", "NONE"

    daily_bias = trend_direction(daily_rates[:-1])
    h4_signal = candle_signal(h4_rates[:-1])
    if daily_bias in {"BUY", "SELL"} and h4_signal == daily_bias:
        return daily_bias, daily_bias
    return "NONE", daily_bias


def get_daily_setup(symbol):
    if not MT5_AVAILABLE or mt5 is None:
        return "NONE", "NONE"

    daily_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 101)
    h4_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 3)
    return daily_setup_from_rates(daily_rates, h4_rates)


def get_daily_signal(symbol):
    signal, _daily_bias = get_daily_setup(symbol)
    return signal

def get_daily_bias(symbol):
    if not MT5_AVAILABLE or mt5 is None:
        return "NONE"
    daily_rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 101)
    if daily_rates is None or len(daily_rates) < 51:
        return "NONE"
    return trend_direction(daily_rates[:-1])
