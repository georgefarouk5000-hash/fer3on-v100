from core.mt5_compat import mt5, MT5_AVAILABLE


def calculate_atr(rates, period=14):
    true_ranges = []
    for i in range(1, len(rates)):
        h  = rates[i]['high']
        l  = rates[i]['low']
        pc = rates[i - 1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 5.0
    return sum(true_ranges[-period:]) / period


def calculate_daily_atr(symbol, period=14):
    """H4 ATR — للاستراتيجية اليومية"""
    rates = mt5.copy_rates_from_pos(
        symbol, mt5.TIMEFRAME_H4, 0, 50
    )
    if rates is None:
        return None
    return calculate_atr(rates, period)


def calculate_swing_atr(symbol, period=14):
    """H1 ATR — لاستراتيجية السوينج"""
    rates = mt5.copy_rates_from_pos(
        symbol, mt5.TIMEFRAME_H1, 0, 50
    )
    if rates is None:
        return None
    return calculate_atr(rates, period)


def calculate_avg_atr(symbol, period=14):
    """
    H1 ATR كمتوسط للمقارنة مع M15 ATR
    يُستخدم لاكتشاف VOLATILE / CRISIS
    """
    rates = mt5.copy_rates_from_pos(
        symbol, mt5.TIMEFRAME_H1, 0, 50
    )
    if rates is None:
        return None
    return calculate_atr(rates, period)
