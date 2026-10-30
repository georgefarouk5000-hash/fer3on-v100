# =========================================
# FER3ON V4 — SMART MONEY ENGINE
# Liquidity Sweep | BOS | FVG | Order Block
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.smc_advanced import analyze_smc_advanced


# =========================================
# 1. LIQUIDITY SWEEP
# وِك فوق القمة أو أسفل القاع ثم انعكاس
# =========================================

def detect_liquidity_sweep(rates, lookback=20):
    if len(rates) < lookback + 2:
        return "NONE"

    window      = rates[-lookback - 1 : -1]
    swing_high  = max(c['high']  for c in window)
    swing_low   = min(c['low']   for c in window)

    last = rates[-1]

    # وِك فوق القمة ثم إغلاق أدنى → أخذ السيولة الشرائية → نزول
    if last['high'] > swing_high and last['close'] < swing_high:
        return "SELL_SWEEP"

    # وِك أسفل القاع ثم إغلاق أعلى → أخذ السيولة البيعية → صعود
    if last['low'] < swing_low and last['close'] > swing_low:
        return "BUY_SWEEP"

    return "NONE"


# =========================================
# 2. BREAK OF STRUCTURE (BOS)
# كسر مستوى هيكل السوق
# =========================================

def detect_bos(rates, lookback=15):
    if len(rates) < lookback + 3:
        return "NONE"

    window     = rates[-lookback - 1 : -2]
    swing_high = max(c['high'] for c in window)
    swing_low  = min(c['low']  for c in window)

    last_close = rates[-1]['close']
    prev_close = rates[-2]['close']

    # إغلاق فوق القمة = BOS صعودي
    if last_close > swing_high and prev_close <= swing_high:
        return "BOS_UP"

    # إغلاق أسفل القاع = BOS هبوطي
    if last_close < swing_low and prev_close >= swing_low:
        return "BOS_DOWN"

    return "NONE"


# =========================================
# 3. FAIR VALUE GAP (FVG)
# فجوة بين 3 شمعات — السعر يعود ليملأها
# =========================================

def detect_fvg(rates, lookback=15):
    """
    Bullish FVG:  candle[i+2].low > candle[i].high
    Bearish FVG:  candle[i+2].high < candle[i].low
    السعر داخل نطاق الـ FVG = إشارة دخول
    """
    if len(rates) < 5:
        return "NONE", None

    current_price = rates[-1]['close']

    # Leave the latest closed candle for a later retest; it cannot create
    # and retest the same gap in one candle.
    for i in range(len(rates) - 4, max(0, len(rates) - lookback), -1):
        c0 = rates[i]
        c1 = rates[i + 1]  # الشمعة المحركة
        c2 = rates[i + 2]

        # ——— Bullish FVG ———
        if c2['low'] > c0['high']:
            zone_top = c2['low']
            zone_bot = c0['high']
            if zone_bot <= current_price <= zone_top:
                return "BUY_FVG", (zone_bot, zone_top)

        # ——— Bearish FVG ———
        elif c2['high'] < c0['low']:
            zone_top = c0['low']
            zone_bot = c2['high']
            if zone_bot <= current_price <= zone_top:
                return "SELL_FVG", (zone_bot, zone_top)

    return "NONE", None


# =========================================
# 4. ORDER BLOCK (OB)
# آخر شمعة عكسية قبل حركة قوية
# السعر يعود إلى نطاق OB = دخول
# =========================================

def detect_order_block(rates, lookback=30):
    if len(rates) < lookback + 5:
        return "NONE", None

    current_price = rates[-1]['close']

    for i in range(len(rates) - 4, max(1, len(rates) - lookback), -1):

        # ——— 3 شمعات صاعدة = حركة قوية للأعلى ———
        bullish_impulse = all(
            rates[j]['close'] > rates[j]['open']
            for j in range(i, i + 3)
        )
        if bullish_impulse:
            # OB = آخر شمعة هابطة قبل الحركة
            ob = rates[i - 1]
            if ob['close'] < ob['open']:
                ob_low  = ob['low']
                ob_high = ob['high']
                if ob_low <= current_price <= ob_high:
                    return "BUY_OB", (ob_low, ob_high)

        # ——— 3 شمعات هابطة = حركة قوية للأسفل ———
        bearish_impulse = all(
            rates[j]['close'] < rates[j]['open']
            for j in range(i, i + 3)
        )
        if bearish_impulse:
            ob = rates[i - 1]
            if ob['close'] > ob['open']:
                ob_low  = ob['low']
                ob_high = ob['high']
                if ob_low <= current_price <= ob_high:
                    return "SELL_OB", (ob_low, ob_high)

    return "NONE", None


# =========================================
# SMC SIGNAL — يجمع كل العوامل
# =========================================

def _analyze_smc_core(rates_h1, rates_m5):
    """Internal SMC scoring — returns buy/sell scores and patterns."""
    buy_score = 0.0
    sell_score = 0.0
    patterns = []

    sweep_h1 = detect_liquidity_sweep(rates_h1, 20)
    if sweep_h1 == "BUY_SWEEP":
        buy_score += 2
        patterns.append("H1_LIQ_SWEEP_BUY")
    elif sweep_h1 == "SELL_SWEEP":
        sell_score += 2
        patterns.append("H1_LIQ_SWEEP_SELL")

    bos_h1 = detect_bos(rates_h1, 15)
    if bos_h1 == "BOS_UP":
        buy_score += 2
        patterns.append("H1_BOS_UP")
    elif bos_h1 == "BOS_DOWN":
        sell_score += 2
        patterns.append("H1_BOS_DOWN")

    sweep_m5 = detect_liquidity_sweep(rates_m5, 20)
    if sweep_m5 == "BUY_SWEEP":
        buy_score += 1
        patterns.append("M5_LIQ_SWEEP_BUY")
    elif sweep_m5 == "SELL_SWEEP":
        sell_score += 1
        patterns.append("M5_LIQ_SWEEP_SELL")

    fvg_sig, fvg_zone = detect_fvg(rates_m5, 15)
    if "BUY" in fvg_sig:
        buy_score += 2
        patterns.append(
            f"FVG_BUY:({float(fvg_zone[0]) if fvg_zone else 0:.2f},"
            f"{float(fvg_zone[1]) if fvg_zone else 0:.2f})"
        )
    elif "SELL" in fvg_sig:
        sell_score += 2
        patterns.append(
            f"FVG_SELL:({float(fvg_zone[0]) if fvg_zone else 0:.2f},"
            f"{float(fvg_zone[1]) if fvg_zone else 0:.2f})"
        )

    ob_sig, ob_zone = detect_order_block(rates_m5, 30)
    if "BUY" in ob_sig:
        buy_score += 2
        patterns.append(
            f"OB_BUY:({float(ob_zone[0]) if ob_zone else 0:.2f},"
            f"{float(ob_zone[1]) if ob_zone else 0:.2f})"
        )
    elif "SELL" in ob_sig:
        sell_score += 2
        patterns.append(
            f"OB_SELL:({float(ob_zone[0]) if ob_zone else 0:.2f},"
            f"{float(ob_zone[1]) if ob_zone else 0:.2f})"
        )

    advanced = analyze_smc_advanced(rates_h1, rates_m5)
    buy_score += advanced.get("buy_score", 0)
    sell_score += advanced.get("sell_score", 0)
    patterns.extend(advanced.get("patterns", []))

    return {
        "buy_score": round(buy_score, 2),
        "sell_score": round(sell_score, 2),
        "patterns": patterns,
        "advanced": advanced,
    }


def get_smc_raw_scores(symbol):
    """
    Extended SMC output with raw buy/sell scores for arbitration.
    Backward-compatible addition — does not change get_smc_signal().
    """
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 60)
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)

    if rates_h1 is None or rates_m5 is None:
        return {
            "signal": "NONE",
            "strength": 0.0,
            "buy_score": 0.0,
            "sell_score": 0.0,
            "patterns": [],
        }

    core = _analyze_smc_core(rates_h1, rates_m5)
    buy_score = core["buy_score"]
    sell_score = core["sell_score"]
    patterns = core["patterns"]

    print(
        f"🏛 SMC | BUY:{buy_score}"
        f" SELL:{sell_score}"
        f" | PD:{core['advanced'].get('premium_discount', {}).get('zone', 'NA')}"
        f" | {patterns}"
    )

    from core.settings import SMC_MIN_SCORE

    if buy_score >= SMC_MIN_SCORE and buy_score > sell_score:
        return {
            "signal": "BUY",
            "strength": buy_score,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "patterns": patterns,
        }
    if sell_score >= SMC_MIN_SCORE and sell_score > buy_score:
        return {
            "signal": "SELL",
            "strength": sell_score,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "patterns": patterns,
        }
    return {
        "signal": "NONE",
        "strength": 0.0,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "patterns": patterns,
    }


def get_smc_signal(symbol):
    """
    يحلل H1 + M5 ويعطي:
      signal   : BUY | SELL | NONE
      strength : 0–9  (نقاط SMC)
      patterns : قائمة الأنماط المؤكَّدة
    """
    raw = get_smc_raw_scores(symbol)
    return raw["signal"], raw["strength"], raw["patterns"]
