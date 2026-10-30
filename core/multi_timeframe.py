# =========================================
# FER3ON V5.2 — MULTI-TIMEFRAME ENGINE
# Structural MTF: CHOCH + BOS + EMA Hybrid
# يدمج التحليل الهيكلي الحقيقي مع EMA
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from core.utils import calculate_ema


# =========================================
# STRUCTURAL TREND من timeframe محدد
# يجمع CHOCH + HH/HL + EMA
# =========================================

def get_structural_trend(symbol, timeframe, lookback=60):
    """
    يحدد اتجاه التريند بطريقة هيكلية مؤسسية:
      - يبحث عن HH/HL (صاعد) أو LH/LL (هابط)
      - يتحقق من BOS حقيقي بالإغلاق
      - يستخدم EMA كمرشح إضافي فقط

    يُعيد: BUY | SELL | NONE، وقوة 0-3
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, lookback)
    if rates is None or len(rates) < 30:
        return "NONE", 0, {}

    highs  = [c["high"]  for c in rates]
    lows   = [c["low"]   for c in rates]
    closes = [c["close"] for c in rates]
    n = len(rates)

    # ————————————————————————
    # PIVOT HIGHS / LOWS
    # ————————————————————————
    pivot_highs = []
    pivot_lows  = []
    for i in range(3, n - 3):
        if highs[i] == max(highs[i-3:i+4]):
            pivot_highs.append((i, highs[i]))
        if lows[i]  == min(lows[i-3:i+4]):
            pivot_lows.append((i, lows[i]))

    # ————————————————————————
    # HH/HL → BULLISH STRUCTURE
    # ————————————————————————
    bullish_score = 0
    bearish_score = 0

    if len(pivot_highs) >= 2:
        if pivot_highs[-1][1] > pivot_highs[-2][1]:
            bullish_score += 1   # Higher High
    if len(pivot_lows) >= 2:
        if pivot_lows[-1][1] > pivot_lows[-2][1]:
            bullish_score += 1   # Higher Low
        if pivot_lows[-1][1] < pivot_lows[-2][1]:
            bearish_score += 1   # Lower Low
    if len(pivot_highs) >= 2:
        if pivot_highs[-1][1] < pivot_highs[-2][1]:
            bearish_score += 1   # Lower High

    # ————————————————————————
    # BOS: إغلاق فوق آخر قمة / تحت آخر قاع
    # ————————————————————————
    last_close = closes[-1]
    split = int(n * 0.65)
    structure_high = max(highs[:split]) if highs[:split] else highs[-1]
    structure_low  = min(lows[:split])  if lows[:split]  else lows[-1]

    bos_up   = last_close > structure_high
    bos_down = last_close < structure_low

    if bos_up:
        bullish_score += 1
    if bos_down:
        bearish_score += 1

    # ————————————————————————
    # EMA FILTER (مرشح إضافي)
    # ————————————————————————
    ema_f = calculate_ema(closes, 20)
    ema_s = calculate_ema(closes, 50)
    ema_bull = ema_f > ema_s
    ema_bear = ema_f < ema_s

    # تأهيل نهائي: يحتاج على الأقل 2 من 3
    if bullish_score >= 2:
        direction = "BUY"
        strength  = bullish_score + (1 if ema_bull else 0)
    elif bearish_score >= 2:
        direction = "SELL"
        strength  = bearish_score + (1 if ema_bear else 0)
    else:
        direction = "NONE"
        strength  = 0

    details = {
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
        "bos_up":        bos_up,
        "bos_down":      bos_down,
        "ema_bull":      ema_bull,
        "structure_high": round(structure_high, 2),
        "structure_low":  round(structure_low, 2),
        "pivot_highs":   [round(p[1],2) for p in pivot_highs[-3:]],
        "pivot_lows":    [round(p[1],2) for p in pivot_lows[-3:]],
    }
    return direction, min(strength, 3), details


# =========================================
# CHOCH-BASED BIAS — من CHOCH Engine
# =========================================

def _get_choch_bias(symbol, timeframe_label):
    """يحاول استيراد CHOCH Engine للتحيز الهيكلي"""
    try:
        from core.choch_engine import detect_choch, detect_real_bos
        tf_map = {
            "D1": mt5.TIMEFRAME_D1,
            "H4": mt5.TIMEFRAME_H4,
            "H1": mt5.TIMEFRAME_H1,
        }
        tf = tf_map.get(timeframe_label, mt5.TIMEFRAME_H4)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 50)
        choch_type, choch_level, strength = detect_choch(rates, lookback=40)
        bos_type,   bos_level,   confirmed = detect_real_bos(rates, lookback=20)

        if choch_type == "CHOCH_BULLISH":
            return "BUY", strength, choch_level
        elif choch_type == "CHOCH_BEARISH":
            return "SELL", strength, choch_level
        elif bos_type == "BOS_UP":
            return "BUY", "MODERATE", bos_level
        elif bos_type == "BOS_DOWN":
            return "SELL", "MODERATE", bos_level
        return "NONE", "WEAK", 0
    except Exception:
        return "NONE", "WEAK", 0


# =========================================
# MTF STRUCTURAL CONSENSUS
# D1 + H4 + H1 — هيكلي حقيقي
# =========================================

def get_mtf_consensus(symbol):
    """
    V5.2: MTF Structural Consensus يدمج:
      - HH/HL/LH/LL (هيكل السوق الحقيقي)
      - BOS (Break of Structure)
      - CHOCH (Change of Character)
      - EMA كمرشح ثانوي فقط

    يُعيد:
      direction  : BUY | SELL | NONE
      strength   : 0-4 (أقوى من V3 الذي كان 0-3)
      structural : True إذا كان التوافق هيكلياً
      details    : dict مفصل
    """
    # ————————————————————————
    # تحليل كل إطار زمني هيكلياً
    # ————————————————————————
    d1_dir, d1_str, d1_det = get_structural_trend(symbol, mt5.TIMEFRAME_D1, lookback=80)
    h4_dir, h4_str, h4_det = get_structural_trend(symbol, mt5.TIMEFRAME_H4, lookback=60)
    h1_dir, h1_str, h1_det = get_structural_trend(symbol, mt5.TIMEFRAME_H1, lookback=40)

    # ————————————————————————
    # CHOCH على H4 للتحيز الكبير
    # ————————————————————————
    choch_dir, choch_str, choch_level = _get_choch_bias(symbol, "H4")

    print(
        f"📊 MTF-STRUCT | D1:{d1_dir}({d1_str})"
        f" H4:{h4_dir}({h4_str})"
        f" H1:{h1_dir}({h1_str})"
        f" CHOCH:{choch_dir}({choch_str})"
    )

    details = {
        "d1": d1_dir, "d1_strength": d1_str, "d1_details": d1_det,
        "h4": h4_dir, "h4_strength": h4_str, "h4_details": h4_det,
        "h1": h1_dir, "h1_strength": h1_str, "h1_details": h1_det,
        "choch": choch_dir, "choch_strength": choch_str,
        "choch_level": choch_level,
    }

    # ————————————————————————
    # SCORING
    # ————————————————————————
    buy_votes  = sum([d1_dir=="BUY", h4_dir=="BUY", h1_dir=="BUY", choch_dir=="BUY"])
    sell_votes = sum([d1_dir=="SELL", h4_dir=="SELL", h1_dir=="SELL", choch_dir=="SELL"])

    # كل الأطر متفقة — إشارة مثالية
    if buy_votes == 4:
        return {"direction":"BUY",  "strength":4, "structural":True, "details":details}
    if sell_votes == 4:
        return {"direction":"SELL", "strength":4, "structural":True, "details":details}

    # 3 من 4
    if buy_votes == 3 and h1_dir == "BUY":
        return {"direction":"BUY",  "strength":3, "structural":True, "details":details}
    if sell_votes == 3 and h1_dir == "SELL":
        return {"direction":"SELL", "strength":3, "structural":True, "details":details}

    # H4 + H1 (الأهم للتنفيذ)
    if h4_dir == h1_dir == "BUY":
        return {"direction":"BUY",  "strength":2, "structural":False, "details":details}
    if h4_dir == h1_dir == "SELL":
        return {"direction":"SELL", "strength":2, "structural":False, "details":details}

    # CHOCH قوي يُرجّح الاتجاه
    if choch_dir in ("BUY","SELL") and choch_str == "STRONG" and h1_dir == choch_dir:
        return {"direction":choch_dir, "strength":2, "structural":True, "details":details}

    return {"direction":"NONE", "strength":0, "structural":False, "details":details}


# =========================================
# MANDATORY CHECK
# =========================================

def mtf_allows_trade(symbol, signal):
    consensus = get_mtf_consensus(symbol)
    direction  = consensus["direction"]
    strength   = consensus["strength"]
    structural = consensus.get("structural", False)

    if direction == "NONE":
        print("❌ MTF-STRUCT: تعارض هيكلي — تداول مرفوض")
        return False, consensus
    if direction != signal:
        print(f"❌ MTF-STRUCT: {direction} vs Signal:{signal} — تعارض")
        return False, consensus

    tag = "STRUCTURAL" if structural else "EMA-ONLY"
    print(f"✅ MTF-STRUCT: {direction} (str={strength}, {tag}) — موافق")
    return True, consensus
