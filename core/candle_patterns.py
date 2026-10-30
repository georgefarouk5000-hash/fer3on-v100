# =========================================
# FER3ON V4.5 — CANDLE PATTERNS
# Hammer | Shooting Star | Engulfing | Doji
# Marubozu | Morning Star | Evening Star
# Three White Soldiers | Three Black Crows
# Inside Bar | Pin Bar
# =========================================


# ==========================================
# HELPERS
# ==========================================

def _body(c):
    return abs(c['close'] - c['open'])

def _range(c):
    return c['high'] - c['low']

def _upper_wick(c):
    return c['high'] - max(c['open'], c['close'])

def _lower_wick(c):
    return min(c['open'], c['close']) - c['low']

def _is_bullish(c):
    return c['close'] > c['open']

def _is_bearish(c):
    return c['close'] < c['open']


# ==========================================
# 1. HAMMER
# ==========================================

def detect_hammer(candle):
    body  = _body(candle)
    rng   = _range(candle)
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)

    if rng == 0:
        return "NONE"

    # XAUUSD Fix: body صغير جداً مقارنة بالرنج في الذهب المتذبذب
    # الشرط الحقيقي: ذيل سفلي >= 2x الجسم + ذيل علوي <= الجسم + جسم موجود فعلاً
    if (lower >= body * 2.0
            and upper <= body * 1.0
            and body / rng >= 0.03):
        return "BUY"
    return "NONE"


# ==========================================
# 2. SHOOTING STAR
# ==========================================

def detect_shooting_star(candle):
    body  = _body(candle)
    rng   = _range(candle)
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)

    if rng == 0:
        return "NONE"

    # XAUUSD Fix: ذيل علوي >= 2x الجسم + ذيل سفلي <= الجسم + جسم موجود فعلاً
    if (upper >= body * 2.0
            and lower <= body * 1.0
            and body / rng >= 0.03):
        return "SELL"
    return "NONE"


# ==========================================
# 3. PIN BAR (احترافي)
# ==========================================

def detect_pin_bar(candle):
    body  = _body(candle)
    rng   = _range(candle)
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)

    if rng == 0 or body == 0:
        return "NONE"

    # Bullish Pin Bar: ذيل سفلي >= 2.5x الجسم + ذيل علوي <= 0.8x الجسم
    # XAUUSD Fix: رفع حد الذيل العلوي من 0.4x إلى 0.8x لاستيعاب تذبذب الذهب
    if (lower >= body * 2.5
            and upper <= body * 0.8
            and body / rng <= 0.40):
        return "BUY"

    # Bearish Pin Bar: ذيل علوي >= 2.5x الجسم + ذيل سفلي <= 0.8x الجسم
    if (upper >= body * 2.5
            and lower <= body * 0.8
            and body / rng <= 0.40):
        return "SELL"

    return "NONE"


# ==========================================
# 4. ENGULFING
# ==========================================

def detect_engulfing(candle, prev_candle):
    if prev_candle is None:
        return "NONE"

    curr_body = _body(candle)
    prev_body = _body(prev_candle)

    # Bullish: شمعة صاعدة تبتلع شمعة هابطة
    if (_is_bullish(candle)
            and _is_bearish(prev_candle)
            and candle['close'] > prev_candle['open']
            and candle['open']  < prev_candle['close']
            and curr_body > prev_body * 0.9):
        return "BUY"

    # Bearish: شمعة هابطة تبتلع شمعة صاعدة
    if (_is_bearish(candle)
            and _is_bullish(prev_candle)
            and candle['close'] < prev_candle['open']
            and candle['open']  > prev_candle['close']
            and curr_body > prev_body * 0.9):
        return "SELL"

    return "NONE"


# ==========================================
# 5. DOJI
# ==========================================

def detect_doji(candle):
    body = _body(candle)
    rng  = _range(candle)

    if rng == 0:
        return "NONE"

    if body / rng <= 0.10:
        return "NEUTRAL"

    return "NONE"


# ==========================================
# 6. MARUBOZU
# ==========================================

def detect_marubozu(candle):
    body  = _body(candle)
    rng   = _range(candle)
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)

    if rng == 0:
        return "NONE"

    if (body / rng >= 0.90
            and upper <= rng * 0.05
            and lower <= rng * 0.05):
        return "BUY" if _is_bullish(candle) else "SELL"

    return "NONE"


# ==========================================
# 7. MORNING STAR (3 شمعات — انعكاس صاعد)
# ==========================================

def detect_morning_star(rates):
    if len(rates) < 3:
        return "NONE"

    c1, c2, c3 = rates[-3], rates[-2], rates[-1]
    c1_body = _body(c1)
    c3_body = _body(c3)

    if c1_body == 0:
        return "NONE"

    c1_mid = (c1['open'] + c1['close']) / 2

    if (_is_bearish(c1)
            and _body(c2) <= c1_body * 0.50
            and _is_bullish(c3)
            and c3['close'] > c1_mid
            and c3_body >= c1_body * 0.50):
        return "BUY"

    return "NONE"


# ==========================================
# 8. EVENING STAR (3 شمعات — انعكاس هابط)
# ==========================================

def detect_evening_star(rates):
    if len(rates) < 3:
        return "NONE"

    c1, c2, c3 = rates[-3], rates[-2], rates[-1]
    c1_body = _body(c1)
    c3_body = _body(c3)

    if c1_body == 0:
        return "NONE"

    c1_mid = (c1['open'] + c1['close']) / 2

    if (_is_bullish(c1)
            and _body(c2) <= c1_body * 0.50
            and _is_bearish(c3)
            and c3['close'] < c1_mid
            and c3_body >= c1_body * 0.50):
        return "SELL"

    return "NONE"


# ==========================================
# 9. THREE WHITE SOLDIERS (ثلاثة جنود بيض)
# ==========================================

def detect_three_white_soldiers(rates):
    if len(rates) < 3:
        return "NONE"

    c1, c2, c3 = rates[-3], rates[-2], rates[-1]

    if not all(_is_bullish(c) for c in [c1, c2, c3]):
        return "NONE"

    if not (c3['close'] > c2['close'] > c1['close']):
        return "NONE"

    if not (c2['open'] >= c1['open'] and c3['open'] >= c2['open']):
        return "NONE"

    # كل شمعة لها جسم معتبر (لا دوجي)
    for c in [c1, c2, c3]:
        if _range(c) > 0 and _body(c) / _range(c) < 0.40:
            return "NONE"

    return "BUY"


# ==========================================
# 10. THREE BLACK CROWS (ثلاثة غربان سود)
# ==========================================

def detect_three_black_crows(rates):
    if len(rates) < 3:
        return "NONE"

    c1, c2, c3 = rates[-3], rates[-2], rates[-1]

    if not all(_is_bearish(c) for c in [c1, c2, c3]):
        return "NONE"

    if not (c3['close'] < c2['close'] < c1['close']):
        return "NONE"

    if not (c2['open'] <= c1['open'] and c3['open'] <= c2['open']):
        return "NONE"

    for c in [c1, c2, c3]:
        if _range(c) > 0 and _body(c) / _range(c) < 0.40:
            return "NONE"

    return "SELL"


# ==========================================
# 11. INSIDE BAR (تردد — محايد)
# ==========================================

def detect_inside_bar(rates):
    if len(rates) < 2:
        return "NONE"

    prev, curr = rates[-2], rates[-1]

    if (curr['high'] <= prev['high']
            and curr['low'] >= prev['low']):
        return "INSIDE"

    return "NONE"


# ==========================================
# 12. MODERN MICROSTRUCTURE PATTERNS
# ==========================================

def detect_liquidity_grab_candle(candle, prev_candle=None):
    body = _body(candle)
    rng = _range(candle)
    if rng == 0 or body == 0:
        return "NONE"
    upper = _upper_wick(candle)
    lower = _lower_wick(candle)
    if upper >= body * 1.8 and lower <= body * 0.4 and body / rng <= 0.35:
        return "SELL"
    if lower >= body * 1.8 and upper <= body * 0.4 and body / rng <= 0.35:
        return "BUY"
    return "NONE"


def detect_stop_hunt_reversal(candle, prev_candle=None):
    if prev_candle is None:
        return "NONE"
    body = _body(candle)
    prev_body = _body(prev_candle)
    if body == 0 or prev_body == 0:
        return "NONE"
    if _is_bullish(candle) and candle['close'] > prev_candle['high'] and body >= prev_body * 0.9:
        return "BUY"
    if _is_bearish(candle) and candle['close'] < prev_candle['low'] and body >= prev_body * 0.9:
        return "SELL"
    return "NONE"


def detect_fake_breakout(candle, prev_candle=None):
    if prev_candle is None:
        return "NONE"
    if candle['high'] > prev_candle['high'] and candle['close'] < prev_candle['high'] - (prev_candle['high'] - prev_candle['low']) * 0.1:
        return "SELL"
    if candle['low'] < prev_candle['low'] and candle['close'] > prev_candle['low'] + (prev_candle['high'] - prev_candle['low']) * 0.1:
        return "BUY"
    return "NONE"


def detect_exhaustion_candle(candle, prev_candle=None):
    body = _body(candle)
    rng = _range(candle)
    if rng == 0:
        return "NONE"
    if body / rng >= 0.85:
        return "BUY" if _is_bullish(candle) else "SELL"
    return "NONE"


def detect_midpoint_reclaim_candle(candle):
    """
    Midpoint reclaim: يفحص إن كانت الشمعة استعادت نصف نطاقها الخاص
    ((high+low)/2) واتّجه إغلاقها في نفس اتجاه هذا الاستعادة.

    ملاحظة الشفافية: هذه الدالة كانت تُسمّى `detect_vwap_reclaim_candle`
    وهي تسمية مضللة — الحساب لا يخص VWAP على الإطلاق (لا يستخدم حجمًا ولا
    سعرًا وسطيًا لعدة شموع، فقط منتصف نطاق الشمعة نفسها). صُحِّحت التسمية،
    وبعد فترة انتقالية (لم يعد أي كود إنتاجي يستدعي الاسم القديم) أُزيل
    الـ alias القديم نفسه — راجع تاريخ git لو احتجت الاسم القديم. لحساب
    VWAP الحقيقي راجع core/anchored_vwap.py.
    """
    body = _body(candle)
    rng = _range(candle)
    if rng == 0 or body == 0:
        return "NONE"
    midpoint = (candle['high'] + candle['low']) / 2.0
    if candle['close'] > midpoint and candle['close'] > candle['open']:
        return "BUY"
    if candle['close'] < midpoint and candle['close'] < candle['open']:
        return "SELL"
    return "NONE"


def detect_delta_reversal_candle(candle, prev_candle=None):
    if prev_candle is None:
        return "NONE"
    if _is_bearish(candle) and _is_bullish(prev_candle) and candle['close'] < prev_candle['open']:
        return "SELL"
    if _is_bullish(candle) and _is_bearish(prev_candle) and candle['close'] > prev_candle['open']:
        return "BUY"
    return "NONE"


def detect_imbalance_sweep_candle(candle, prev_candle=None):
    if prev_candle is None:
        return "NONE"
    if candle['open'] < prev_candle['low'] and candle['close'] > prev_candle['open']:
        return "BUY"
    if candle['open'] > prev_candle['high'] and candle['close'] < prev_candle['open']:
        return "SELL"
    return "NONE"


def detect_micro_bos_candle(candle, prev_candle=None):
    if prev_candle is None:
        return "NONE"
    if candle['close'] > prev_candle['high'] and candle['close'] > candle['open']:
        return "BUY"
    if candle['close'] < prev_candle['low'] and candle['close'] < candle['open']:
        return "SELL"
    return "NONE"


# ==========================================
# MASTER DETECTOR — يعيد (pattern, direction, weight)
# weight: 1=بسيط | 2=متوسط | 3=قوي
# ==========================================

def detect_candle_pattern(rates):
    """يعيد signal: BUY | SELL | NONE"""
    result = detect_candle_pattern_full(rates)
    return result[1]


def detect_candle_pattern_full(rates):
    """
    يعيد: (pattern_name, direction, weight)
    direction: BUY | SELL | NONE
    weight   : 1 | 2 | 3
    """
    if rates is None or len(rates) < 3:
        return ("NONE", "NONE", 0)

    last = rates[-1]

    # --- 3-candle patterns (weight 3 — أقوى) ---
    ms = detect_morning_star(rates)
    if ms != "NONE":
        return ("MORNING_STAR", ms, 3)

    es = detect_evening_star(rates)
    if es != "NONE":
        return ("EVENING_STAR", es, 3)

    tws = detect_three_white_soldiers(rates)
    if tws != "NONE":
        return ("THREE_WHITE_SOLDIERS", tws, 3)

    tbc = detect_three_black_crows(rates)
    if tbc != "NONE":
        return ("THREE_BLACK_CROWS", tbc, 3)

    # --- 2-candle patterns (weight 2) ---
    eng = detect_engulfing(last, rates[-2])
    if eng != "NONE":
        return ("ENGULFING", eng, 2)

    liq_grab = detect_liquidity_grab_candle(last, rates[-2])
    if liq_grab != "NONE":
        return ("LIQUIDITY_GRAB_CANDLE", liq_grab, 3)

    stop_hunt = detect_stop_hunt_reversal(last, rates[-2])
    if stop_hunt != "NONE":
        return ("STOP_HUNT_REVERSAL", stop_hunt, 3)

    fake_break = detect_fake_breakout(last, rates[-2])
    if fake_break != "NONE":
        return ("FAKE_BREAKOUT", fake_break, 2)

    exhaustion = detect_exhaustion_candle(last, rates[-2])
    if exhaustion != "NONE":
        return ("EXHAUSTION_CANDLE", exhaustion, 2)

    # ملاحظة تسمية: النمط هنا هو Midpoint Reclaim (استعادة منتصف نطاق الشمعة)
    # وليس VWAP الحقيقي — تركنا الاسم الظاهر MIDPOINT_RECLAIM_CANDLE ليعكس
    # الحساب فعليًا. لحساب VWAP الحقيقي (بالحجم) راجع core/anchored_vwap.py.
    midpoint_reclaim = detect_midpoint_reclaim_candle(last)
    if midpoint_reclaim != "NONE":
        return ("MIDPOINT_RECLAIM_CANDLE", midpoint_reclaim, 2)

    delta_reversal = detect_delta_reversal_candle(last, rates[-2])
    if delta_reversal != "NONE":
        return ("DELTA_REVERSAL_CANDLE", delta_reversal, 2)

    imbalance = detect_imbalance_sweep_candle(last, rates[-2])
    if imbalance != "NONE":
        return ("IMBALANCE_SWEEP_CANDLE", imbalance, 2)

    micro_bos = detect_micro_bos_candle(last, rates[-2])
    if micro_bos != "NONE":
        return ("MICRO_BOS_CANDLE", micro_bos, 2)

    ib = detect_inside_bar(rates)
    if ib == "INSIDE":
        return ("INSIDE_BAR", "NONE", 1)

    # --- 1-candle patterns (weight 2) ---
    pb = detect_pin_bar(last)
    if pb != "NONE":
        return ("PIN_BAR", pb, 2)

    maru = detect_marubozu(last)
    if maru != "NONE":
        return ("MARUBOZU", maru, 2)

    hammer = detect_hammer(last)
    if hammer != "NONE":
        return ("HAMMER", hammer, 1)

    ss = detect_shooting_star(last)
    if ss != "NONE":
        return ("SHOOTING_STAR", ss, 1)

    doji = detect_doji(last)
    if doji == "NEUTRAL":
        return ("DOJI", "NONE", 1)

    return ("NONE", "NONE", 0)
