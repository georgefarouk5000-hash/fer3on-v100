# =========================================
# FER3ON V5.1 — SURVIVAL INTELLIGENCE
# لا يتوقف عن إيجاد طريق للربح
# حتى في أصعب الأوقات بذكاء
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone
from core.settings import get_min_sl_dollars


# =========================================
# MARKET CONDITION ANALYZER
# تحليل حالة السوق الكاملة
# =========================================

def analyze_market_condition(symbol, atr, market_regime):
    """
    يُحدد أفضل استراتيجية في أي حالة سوق.

    يُعيد:
      condition      : TRENDING | RANGING | VOLATILE | THIN | CRISIS
      best_strategy  : الاستراتيجية المناسبة
      lot_mult       : معامل حجم اللوت
      timing_advice  : وقت الدخول المناسب
      adaptations    : قائمة بالتكيفات المقترحة
    """
    now_utc   = datetime.now(timezone.utc)
    hour      = now_utc.hour
    weekday   = now_utc.weekday()

    adaptations = []

    # =========================================
    # اكتشاف حالة السوق الدقيقة
    # =========================================
    condition = "NORMAL"

    # سوق رفيع (قليل السيولة)
    thin_hours = (hour < 7) or (hour >= 21)
    thin_days  = weekday in (4, 5, 6)  # الجمعة بعد 18 + عطلة
    if thin_hours or thin_days:
        condition = "THIN"
        adaptations.append("THIN_MARKET: تقليص الحجم + SL أوسع")

    elif market_regime == "CRISIS":
        condition = "CRISIS"
        adaptations.append("CRISIS: SMC فقط + حجم 50%")

    elif market_regime == "VOLATILE":
        condition = "VOLATILE"
        adaptations.append("VOLATILE: DAILY فقط + SL أوسع")

    elif market_regime == "TRENDING":
        condition = "TRENDING"
        adaptations.append("TRENDING: SMC مناسب مع ضبط الحجم حسب المخاطر")

    elif market_regime == "RANGING":
        condition = "RANGING"
        adaptations.append("RANGING: SMC أفضل + اصبر على الـ Retest")

    # =========================================
    # أفضل استراتيجية لكل حالة
    # =========================================
    CONDITION_STRATEGY = {
        "TRENDING": "SMC",
        "RANGING":  "SMC",
        "VOLATILE": "DAILY",
        "THIN":     "SMC",
        "CRISIS":   "SMC",
        "NORMAL":   "SMC",
    }

    best_strategy = CONDITION_STRATEGY.get(condition, "SMC")

    # =========================================
    # معامل الحجم حسب الحالة
    # =========================================
    LOT_MULT = {
        "TRENDING": 1.00,
        "RANGING":  0.85,
        "VOLATILE": 0.60,
        "THIN":     0.50,
        "CRISIS":   0.40,
        "NORMAL":   1.00,
    }
    lot_mult = LOT_MULT.get(condition, 1.0)

    # =========================================
    # توصيات التوقيت
    # =========================================
    if 8 <= hour < 13:
        timing_advice = "LONDON_PRIME — أفضل وقت للدخول"
    elif 13 <= hour < 17:
        timing_advice = "NY_LONDON_OVERLAP — ذروة السيولة"
    elif 17 <= hour < 21:
        timing_advice = "NY_PRIME — وقت جيد"
    elif 0 <= hour < 4:
        timing_advice = "ASIA_PRIME — للـ Range plays فقط"
    else:
        timing_advice = "OFF_HOURS — انتظر جلسة رئيسية"

    print(
        f"🛡 SURVIVAL: Cond={condition}"
        f" | Best={best_strategy}"
        f" | LotMult={lot_mult}"
        f" | Timing={timing_advice}"
    )

    return {
        "condition":      condition,
        "best_strategy":  best_strategy,
        "lot_mult":       lot_mult,
        "timing_advice":  timing_advice,
        "adaptations":    adaptations,
        "hour":           hour,
        "is_prime_time":  (8 <= hour < 17),
    }


# =========================================
# ADAPTIVE ENTRY FINDER
# يجد طريقاً للدخول في أي ظرف
# =========================================

def find_adaptive_entry(
    symbol,
    signal,
    strategy,
    atr,
    condition_data,
    choch_data=None,
    liq_map=None
):
    """
    يجد نقطة دخول ذكية متكيفة مع الظروف.

    يُعيد:
      entry_valid  : bool
      entry_type   : IMMEDIATE | LIMIT | WAIT
      entry_price  : السعر المقترح
      sl_dist      : المسافة المقترحة للـ SL
      tp_dist      : المسافة المقترحة للـ TP
      lot_mult     : معامل الحجم
      reason       : الشرح
    """
    condition = condition_data.get("condition", "NORMAL")
    lot_mult  = condition_data.get("lot_mult", 1.0)

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return {"entry_valid": False, "reason": "NO_TICK"}

    current_price = (tick.ask + tick.bid) / 2

    adaptive = calculate_adaptive_sl_tp(
        atr=atr,
        strategy='SURVIVAL',
        lot=lot_mult,
        confidence=0.6,
        quality_score=70.0,
        market_regime=condition,
        session='UNKNOWN',
        structure_strength=0.6,
        liquidity=0.6,
        volatility=0.5,
        spread=0.0,
        execution_grade='B',
        broker_stop_level=0.0,
        broker_stop_fallback=0.0,
        min_sl=get_min_sl_dollars(),
    )
    sl_dist = adaptive['sl_distance']
    tp_dist = adaptive['tp_distance']

    # =========================================
    # تحسين بناءً على Liquidity Map
    # =========================================
    entry_type = "IMMEDIATE"

    if liq_map and liq_map.get("liquidity_score", 0) >= 8:
        next_target  = liq_map.get("next_target", 0)
        dist_to_next = liq_map.get("distance_next", 0)

        if dist_to_next > 0:
            # ضبط TP ليلامس هدف السيولة
            if (signal == "BUY"  and next_target > current_price) or \
               (signal == "SELL" and next_target < current_price):
                tp_dist = round(dist_to_next * 0.90, 2)   # 90% من المسافة

    # =========================================
    # تحسين بناءً على CHOCH
    # =========================================
    if choch_data and choch_data.get("bias") == signal:
        choch_level = choch_data.get("choch_level", 0)
        if choch_level > 0:
            # SL تحت/فوق مستوى CHOCH
            if signal == "BUY":
                sl_from_choch = abs(current_price - choch_level) + atr * 0.3
            else:
                sl_from_choch = abs(current_price - choch_level) + atr * 0.3

            if sl_from_choch < sl_dist * 1.5:
                sl_dist = round(sl_from_choch, 2)

    rr = tp_dist / sl_dist if sl_dist > 0 else 0

    entry_price = tick.ask if signal == "BUY" else tick.bid

    print(
        f"🎯 ADAPTIVE ENTRY | Cond:{condition}"
        f" | Type:{entry_type}"
        f" | SL:{sl_dist:.1f} TP:{tp_dist:.1f}"
        f" | RR:{rr:.2f}"
        f" | LotMult:{lot_mult}"
    )

    return {
        "entry_valid":  True,
        "entry_type":   entry_type,
        "entry_price":  round(entry_price, 2),
        "sl_dist":      sl_dist,
        "tp_dist":      tp_dist,
        "rr_ratio":     round(rr, 2),
        "lot_mult":     lot_mult,
        "condition":    condition,
        "reason":       f"{condition}_{strategy}_{entry_type}",
    }


# =========================================
# NO-TRADE ALTERNATIVE (عندما لا تتاح صفقة)
# =========================================

def suggest_alternative_action(
    brain_blocked,
    market_condition,
    session
):
    """
    عندما يُوقف البوت الدخول، يقترح بديلاً ذكياً
    بدلاً من الانتظار السلبي.

    يُعيد:
      action    : WAIT | SWITCH_STRATEGY | REDUCE_SIZE
      advice    : نص الاقتراح
    """
    block_reason = brain_blocked if isinstance(brain_blocked, str) else "UNKNOWN"

    if "CRISIS" in block_reason:
        return {
            "action": "WAIT",
            "advice": "🛡 أزمة سوق — انتظر حتى يستقر. تحقق من الأخبار."
        }

    if "LOW_SCORE" in block_reason:
        return {
            "action": "SWITCH_STRATEGY",
            "advice": "📊 نقاط منخفضة — جرب SMC بدلاً من الإستراتيجية الحالية"
        }

    if "NO_VALID_SIGNALS" in block_reason:
        if market_condition == "RANGING":
            return {
                "action": "REDUCE_SIZE",
                "advice": "🔄 السوق في Range — خفّض الحجم وانتظر تأكيد البنية"
            }
        else:
            return {
                "action": "WAIT",
                "advice": "⏳ لا إشارات حالياً — انتظر BOS/CHOCH"
            }

    if "OFF_SESSION" in block_reason or session == "OFF_HOURS":
        return {
            "action": "WAIT",
            "advice": "🌙 خارج أوقات التداول — انتظر جلسة لندن (8:00 UTC)"
        }

    return {
        "action": "WAIT",
        "advice": "⏳ انتظر إشارة أوضح..."
    }
