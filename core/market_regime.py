# =========================================
# FER3ON V5.2 — MARKET REGIME
# الإصلاح: rates_h1 is not None بدل if rates_h1
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.atr_manager import calculate_atr
from core.utils import calculate_ema
from core.settings import VOLATILE_MULT, CRISIS_MULT


# =============================================================================
# V7 — REGIME STRATEGY WEIGHTS (مرن، غير ثنائي، لا حظر)
# =============================================================================
# REGIME_STRATEGY_FIT is consumed as a sizing modifier by trade_executor.
# =============================================================================

REGIME_STRATEGY_FIT = {
    "TRENDING": {"DAILY": 1.15, "SMC": 1.05},
    "RANGING":  {"DAILY": 0.80, "SMC": 0.95},
    "VOLATILE": {"DAILY": 0.70, "SMC": 0.85},
    "CRISIS":   {"DAILY": 0.50, "SMC": 0.60},
    "UNKNOWN":  {"DAILY": 1.00, "SMC": 1.00},
}


def get_regime_fit_multiplier(strategy, regime):
    """
    يُرجع معامل توافق الاستراتيجية مع حالة السوق الحالية — لا حظر أبدًا،
    فقط تصغير/تكبير محدود (نطاق القيم في REGIME_STRATEGY_FIT بين 0.50 و1.15).
    قيمة افتراضية آمنة 1.0 لأي استراتيجية أو regime غير معروف.
    """
    strat_key = str(strategy or "").upper()
    regime_key = str(regime or "UNKNOWN").upper()
    regime_table = REGIME_STRATEGY_FIT.get(regime_key, REGIME_STRATEGY_FIT["UNKNOWN"])
    return float(regime_table.get(strat_key, 1.0))


def detect_market_regime(symbol, *, rates_m15=None, rates_h1=None):
    if rates_m15 is None:
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    if rates_m15 is None or len(rates_m15) < 10:
        return "UNKNOWN"

    atr = calculate_atr(rates_m15)

    if rates_h1 is None:
        rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    avg_atr = atr
    if rates_h1 is not None and len(rates_h1) > 10:
        avg_atr = sum(c["high"] - c["low"] for c in rates_h1) / len(rates_h1)

    crisis_thresh = round(avg_atr * CRISIS_MULT, 2)
    volatile_thresh = round(avg_atr * VOLATILE_MULT, 2)

    print(
        f"📊 REGIME | M15_ATR:{atr:.2f}"
        f" H1_AVG:{avg_atr:.2f}"
        f" | CRISIS>{crisis_thresh}"
        f" VOLATILE>{volatile_thresh}"
    )

    if atr > avg_atr * CRISIS_MULT:
        print("🚨 REGIME: CRISIS")
        return "CRISIS"

    if atr > avg_atr * VOLATILE_MULT:
        print("⚠️  REGIME: VOLATILE")
        return "VOLATILE"

    closes = [c["close"] for c in rates_m15]
    ema_fast = calculate_ema(closes, 20)
    ema_slow = calculate_ema(closes, 50)
    trend_strength = abs(ema_fast - ema_slow)

    if trend_strength > atr * 0.8:
        direction = "UP" if ema_fast > ema_slow else "DOWN"
        print(f"📈 REGIME: TRENDING ({direction})")
        return "TRENDING"

    print("↔️  REGIME: RANGING")
    return "RANGING"
