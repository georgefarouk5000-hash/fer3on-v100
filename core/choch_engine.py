# =========================================
# FER3ON V5.1 — CHOCH ENGINE
# Change Of Character — Priority #1
# BOS + CHOCH = Complete Structure Analysis
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE


# =========================================
# DETECT CHOCH (Change Of Character)
# أول كسر عكسي بعد هيكل ممتد
# =========================================

def detect_choch(rates, lookback=30):
    """
    يكتشف Change Of Character:
      - في اتجاه صاعد: أول LL بعد سلسلة HH/HL = CHOCH هبوطي
      - في اتجاه هابط: أول HH بعد سلسلة LH/LL = CHOCH صعودي

    يُعيد:
      choch_type  : CHOCH_BULLISH | CHOCH_BEARISH | NONE
      choch_level : مستوى السعر الذي حدث عنده الـ CHOCH
      strength    : STRONG | MODERATE | WEAK
    """
    if rates is None or len(rates) < lookback:
        return "NONE", 0, "WEAK"

    recent = rates[-lookback:]
    n = len(recent)

    # نبني سلسلة من القمم والقيعان
    highs = [c["high"]  for c in recent]
    lows  = [c["low"]   for c in recent]
    closes= [c["close"] for c in recent]

    # نحدد آخر pivot highs و pivot lows
    pivot_highs = []
    pivot_lows  = []

    for i in range(2, n - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            pivot_highs.append((i, highs[i]))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            pivot_lows.append((i, lows[i]))

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "NONE", 0, "WEAK"

    # =========================================
    # CHOCH BEARISH: في هيكل صاعد، أول LL
    # =========================================
    # نتحقق من وجود هيكل صاعد أخيراً (HH + HL)
    last_highs = pivot_highs[-3:] if len(pivot_highs) >= 3 else pivot_highs
    last_lows  = pivot_lows[-3:]  if len(pivot_lows)  >= 3 else pivot_lows

    bullish_struct = all(
        last_highs[i][1] > last_highs[i-1][1]
        for i in range(1, len(last_highs))
    )
    bearish_struct = all(
        last_lows[i][1] < last_lows[i-1][1]
        for i in range(1, len(last_lows))
    )

    # CHOCH BEARISH: هيكل صاعد → ثم LL
    if bullish_struct and len(pivot_lows) >= 2:
        last_low  = pivot_lows[-1][1]
        prev_low  = pivot_lows[-2][1]
        last_close = closes[-1]

        if last_low < prev_low and last_close < prev_low:
            # قياس قوة الـ CHOCH
            drop_pct = (prev_low - last_low) / prev_low * 100
            if drop_pct > 0.5:
                strength = "STRONG"
            elif drop_pct > 0.2:
                strength = "MODERATE"
            else:
                strength = "WEAK"

            choch_level = prev_low
            print(f"⚡ CHOCH BEARISH detected @ {choch_level:.2f} | Strength:{strength}")
            return "CHOCH_BEARISH", choch_level, strength

    # CHOCH BULLISH: هيكل هابط → ثم HH
    if bearish_struct and len(pivot_highs) >= 2:
        last_high = pivot_highs[-1][1]
        prev_high = pivot_highs[-2][1]
        last_close = closes[-1]

        if last_high > prev_high and last_close > prev_high:
            rise_pct = (last_high - prev_high) / prev_high * 100
            if rise_pct > 0.5:
                strength = "STRONG"
            elif rise_pct > 0.2:
                strength = "MODERATE"
            else:
                strength = "WEAK"

            choch_level = prev_high
            print(f"⚡ CHOCH BULLISH detected @ {choch_level:.2f} | Strength:{strength}")
            return "CHOCH_BULLISH", choch_level, strength

    return "NONE", 0, "WEAK"


# =========================================
# DETECT REAL BOS (Break Of Structure)
# الكسر الحقيقي المؤسسي
# =========================================

def detect_real_bos(rates, lookback=20):
    """
    يكتشف BOS حقيقي:
      - BOS_UP:   كسر أعلى قمة هيكلية سابقة بإغلاق
      - BOS_DOWN: كسر أدنى قاع هيكلي سابق بإغلاق

    يُعيد:
      bos_type  : BOS_UP | BOS_DOWN | NONE
      bos_level : مستوى الكسر
      confirmed : هل أُغلقت شمعة فوق/تحت المستوى
    """
    if rates is None or len(rates) < lookback:
        return "NONE", 0, False

    recent = rates[-lookback:]
    n = len(recent)

    highs  = [c["high"]  for c in recent]
    lows   = [c["low"]   for c in recent]
    closes = [c["close"] for c in recent]

    # أعلى قمة في أول 70% من الفترة
    split = int(n * 0.7)
    structure_high = max(highs[:split])
    structure_low  = min(lows[:split])

    # هل الإغلاق الأخير كسر الهيكل؟
    last_close = closes[-1]
    last_high  = highs[-1]
    last_low   = lows[-1]

    if last_close > structure_high and last_high > structure_high:
        print(f"✅ BOS UP confirmed @ {structure_high:.2f}")
        return "BOS_UP", structure_high, True

    if last_close < structure_low and last_low < structure_low:
        print(f"✅ BOS DOWN confirmed @ {structure_low:.2f}")
        return "BOS_DOWN", structure_low, True

    return "NONE", 0, False


# =========================================
# GET FULL STRUCTURE ANALYSIS (BOS + CHOCH)
# =========================================

def get_full_structure_analysis(symbol):
    """
    التحليل الهيكلي الكامل المؤسسي:
      H4 → CHOCH (تحديد التحول الكبير)
      H1 → BOS   (تأكيد الكسر)
      M15 → CHOCH (دقة الدخول)

    يُعيد:
      choch_h4     : نوع CHOCH على H4
      choch_m15    : نوع CHOCH على M15
      bos_h1       : نوع BOS على H1
      bias         : BUY | SELL | NEUTRAL
      confirmation : STRONG | MODERATE | WEAK
      choch_level  : مستوى CHOCH الرئيسي
    """
    rates_h4  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 60)
    rates_h1  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 50)
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 40)

    # H4 CHOCH
    choch_h4, h4_level, h4_strength = detect_choch(rates_h4, lookback=40) \
        if rates_h4 is not None else ("NONE", 0, "WEAK")

    # H1 BOS
    bos_h1, bos_level, bos_confirmed = detect_real_bos(rates_h1, lookback=20) \
        if rates_h1 is not None else ("NONE", 0, False)

    # M15 CHOCH (دقة الدخول)
    choch_m15, m15_level, m15_strength = detect_choch(rates_m15, lookback=20) \
        if rates_m15 is not None else ("NONE", 0, "WEAK")

    # تحديد الـ BIAS
    bias = "NEUTRAL"
    confirmation = "WEAK"
    choch_level = 0

    # BULLISH: CHOCH_BULLISH على H4 + BOS_UP على H1
    if choch_h4 == "CHOCH_BULLISH":
        bias = "BUY"
        choch_level = h4_level
        if bos_h1 == "BOS_UP":
            confirmation = "STRONG" if h4_strength == "STRONG" else "MODERATE"
        else:
            confirmation = "MODERATE" if h4_strength == "STRONG" else "WEAK"

    # BEARISH: CHOCH_BEARISH على H4 + BOS_DOWN على H1
    elif choch_h4 == "CHOCH_BEARISH":
        bias = "SELL"
        choch_level = h4_level
        if bos_h1 == "BOS_DOWN":
            confirmation = "STRONG" if h4_strength == "STRONG" else "MODERATE"
        else:
            confirmation = "MODERATE" if h4_strength == "STRONG" else "WEAK"

    # بدون CHOCH كبير، نعتمد BOS فقط (moderate)
    elif bos_h1 == "BOS_UP":
        bias = "BUY"
        choch_level = bos_level
        confirmation = "MODERATE"
    elif bos_h1 == "BOS_DOWN":
        bias = "SELL"
        choch_level = bos_level
        confirmation = "MODERATE"

    # M15 CHOCH يعزز الدخول (precision entry)
    entry_precision = "NORMAL"
    if (choch_m15 == "CHOCH_BULLISH" and bias == "BUY") or \
       (choch_m15 == "CHOCH_BEARISH" and bias == "SELL"):
        entry_precision = "PRECISE"

    print(
        f"⚡ CHOCH+BOS | H4:{choch_h4}({h4_strength})"
        f" H1_BOS:{bos_h1}"
        f" M15:{choch_m15}"
        f" → BIAS:{bias} | CONFIRM:{confirmation}"
        f" | PRECISION:{entry_precision}"
    )

    return {
        "choch_h4":        choch_h4,
        "choch_m15":       choch_m15,
        "bos_h1":          bos_h1,
        "bias":            bias,
        "confirmation":    confirmation,
        "choch_level":     choch_level,
        "bos_level":       bos_level,
        "entry_precision": entry_precision,
        "h4_strength":     h4_strength,
        "m15_strength":    m15_strength,
    }


# =========================================
# CHOCH SCORE للـ Confidence Engine
# =========================================

def get_choch_score(choch_data, signal):
    """
    يُعيد نقطة إضافية للـ Confidence Engine (0-15)
      STRONG + signal match  → 15
      MODERATE + match       → 10
      WEAK + match           → 5
      NONE                   → 0
      Conflict               → -5
    """
    bias = choch_data.get("bias", "NEUTRAL")
    conf = choch_data.get("confirmation", "WEAK")

    if bias == signal:
        if conf == "STRONG":
            return 15
        elif conf == "MODERATE":
            return 10
        else:
            return 5
    elif bias not in ("NEUTRAL",) and bias != signal:
        return -5
    return 0
