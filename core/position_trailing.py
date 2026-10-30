# =========================================
# FER3ON — SMART TRAILING + BREAK-EVEN
# مرحلتان:
# Stage 1: +1R  → نقل SL لـ Break-Even
# Stage 2: +2R  → ATR Trailing (ضيق تدريجياً)
#
# V3.6 UPDATE: trailing covers current and legacy positions with ATR profiles
# for active strategies and a safe shared fallback for older trades.
#   ALIGNED  → مساحة تنفّس كاملة (يتبع الترند بثقة)
#   NEUTRAL  → معامل متوسط
#   CONFLICT → مسافة أضيق (حماية أسرع لرأس المال، بدون وقف الصفقة)
# هذا "ذكي ومرن" — لا متهور (يحمي وقت الشك) ولا متشدد (يعطي مساحة وقت التوافق).
# SMC تحديدًا: التريلينج المتدرج لا يُفعَّل إلا بعد تحقق TP1 (break-even أولاً) —
# يُطبَّق هنا عبر اعتبار Stage 1 (BE) كبديل لـ TP1 لو لم تتوفر بيانات TP1 الفعلية.
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from core.demo_execution import demo_execution_status

from core.settings import (
    SMC_MAGIC,
    DAILY_MAGIC,
    BREAK_EVEN_ENABLED,
    BREAK_EVEN_R1,
    BREAK_EVEN_BUFFER,
    TRAILING_R2,
    ATR_TRAIL_MULT,
    MIN_TRAIL,
    TRAILING_BASE_ATR_MULT,
    TRAILING_ALIGNMENT_FACTOR,
    TRAILING_SMC_REQUIRES_TP1,
    TRAILING_MIN_DISTANCE_BY_STRATEGY,
    MAX_SL_DISTANCE_DOLLARS,
)
from core.trade_identity import LEGACY_MAGIC_TO_STRATEGY, strategy_from_magic


_ALL_MANAGED_MAGICS = {SMC_MAGIC, DAILY_MAGIC, *LEGACY_MAGIC_TO_STRATEGY}


def _daily_swing_distance(symbol: str, price: float, direction: str) -> float:
    """
    V3.6: يحسب المسافة (بالسعر، لا بالنقاط) بين السعر الحالي وآخر قاع/قمة D1
    مغلقة (Swing-based trailing — مطابق لـ core/daily_trade_manager.py
    الأصلية، لكن كحساب مسافة هنا بدل order_send منفصل، لتفادي تعارض
    تعديلين منفصلين لنفس SL في الدورة الواحدة).

    يُستخدم فقط كـ"حد أدنى إضافي" لـ DAILY — يُؤخَذ الأبعد (الأكثر حماية
    تنفّسًا) بينه وبين ATR-trailing العادي، أبدًا لا يُضيِّق الحماية.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)
        if rates is None or len(rates) < 2:
            return 0.0
        previous_candle = rates[-2]
        if direction == "BUY":
            return max(0.0, price - float(previous_candle["low"]))
        else:
            return max(0.0, float(previous_candle["high"]) - price)
    except Exception:
        return 0.0


def _resolve_trail_distance(
    strategy: str,
    atr: float,
    mtf_mode: str = "ALIGNED",
    symbol: str = None,
    price: float = None,
    direction: str = None,
) -> float:
    """
    V3.6: يحسب trailing distance حسب الاستراتيجية الحالية + حالة المحاذاة، بدل
    ATR_TRAIL_MULT الثابت الواحد للجميع. يبقى MIN_TRAIL كحد أدنى مطلق دائمًا.

    لـ DAILY تحديدًا: يُقارَن بمسافة Swing-based (آخر قاع/قمة D1) ويُؤخذ
    الأبعد بين الاثنين — مساحة تنفّس أوسع دائمًا، لا أضيق، تطبيقًا لمبدأ
    "مرن وذكي وغير متهور وغير متشدد" (لا تُفضَّل قيمة على حساب تضييق الحماية).
    """
    strat = str(strategy or "").upper()
    base_mult = TRAILING_BASE_ATR_MULT.get(strat, ATR_TRAIL_MULT)
    align_factor = TRAILING_ALIGNMENT_FACTOR.get(str(mtf_mode or "ALIGNED").upper(), 1.0)
    min_dist = TRAILING_MIN_DISTANCE_BY_STRATEGY.get(strat, MIN_TRAIL)
    atr_dist = min(
        max(atr * base_mult * align_factor, min_dist),
        float(MAX_SL_DISTANCE_DOLLARS),
    )

    if strat == "DAILY" and symbol and price is not None and direction:
        swing_dist = _daily_swing_distance(symbol, price, direction)
        if swing_dist > 0:
            return max(atr_dist, swing_dist)

    return atr_dist


def update_position_trailing(symbol, atr, mtf_modes=None):
    """Manage open positions with break-even and adaptive ATR trailing.

    Parameters
    ----------
    mtf_modes : dict اختياري {ticket: "ALIGNED"|"NEUTRAL"|"CONFLICT"}.
                لو غير متوفر لصفقة معيّنة، تُستخدم "ALIGNED" (السلوك الأصلي
                — مساحة تنفّس كاملة بدون تضييق إضافي) كقيمة افتراضية آمنة.

    """
    positions   = mt5.positions_get(symbol=symbol)
    symbol_info = mt5.symbol_info(symbol)
    tick        = mt5.symbol_info_tick(symbol)

    if not positions or not symbol_info or not tick:
        return

    mtf_modes = mtf_modes or {}
    min_stop   = symbol_info.trade_stops_level * symbol_info.point
    digits     = symbol_info.digits

    for pos in positions:

        if pos.magic not in _ALL_MANAGED_MAGICS:
            continue

        ticket     = pos.ticket
        entry      = pos.price_open
        current_sl = pos.sl
        tp         = pos.tp
        strat      = strategy_from_magic(pos.magic, default="SMC")

        # V3.6: مضاعف ATR ديناميكي حسب الاستراتيجية + حالة محاذاة هذه الصفقة
        pos_mtf_mode = mtf_modes.get(ticket, "ALIGNED")
        pos_direction = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
        _live_price = tick.bid if pos_direction == "BUY" else tick.ask
        trail_dist = _resolve_trail_distance(
            strat, atr, pos_mtf_mode,
            symbol=symbol, price=_live_price, direction=pos_direction,
        )

        new_sl     = None
        stage_msg  = ""

        # ==========================================
        # BUY POSITION
        # ==========================================
        if pos.type == mt5.POSITION_TYPE_BUY:

            price = tick.bid

            # sl_dist_original: المسافة الأصلية للـ SL
            # إذا SL < entry → لم نصل break-even بعد
            # إذا SL >= entry → نحن في Stage 2 أو بعده

            if current_sl > 0 and current_sl < entry:
                # --- Stage 1: هل وصلنا +1R؟ ---
                sl_dist = entry - current_sl
                profit  = price - entry

                if (BREAK_EVEN_ENABLED
                        and profit >= sl_dist * BREAK_EVEN_R1):
                    be_sl = round(entry + BREAK_EVEN_BUFFER, digits)
                    if be_sl > current_sl:
                        new_sl    = be_sl
                        stage_msg = "STAGE1_BE"

            elif current_sl >= entry or current_sl == 0:
                # --- Stage 2: ATR trailing ---
                # SMC: التريلينج المتدرج بعد TP1 فقط — بما أن وصول Stage 2
                # هنا يعني أصلاً أن break-even (Stage 1) تحقق، هذا يُعتبر
                # بديلاً عمليًا لشرط "بعد TP1" المطلوب لـ SMC تحديدًا.
                if strat == "SMC" and TRAILING_SMC_REQUIRES_TP1 and current_sl < entry:
                    pass  # لم يتحقق الشرط بعد — لا تريلينج قبل BE لـ SMC
                else:
                    trail_sl = round(price - trail_dist, digits)

                    if (trail_sl > (current_sl or 0)
                            and (price - trail_sl) >= min_stop):
                        new_sl    = trail_sl
                        stage_msg = "STAGE2_TRAIL"

        # ==========================================
        # SELL POSITION
        # ==========================================
        elif pos.type == mt5.POSITION_TYPE_SELL:

            price = tick.ask

            if current_sl > 0 and current_sl > entry:
                # --- Stage 1 ---
                sl_dist = current_sl - entry
                profit  = entry - price

                if (BREAK_EVEN_ENABLED
                        and profit >= sl_dist * BREAK_EVEN_R1):
                    be_sl = round(entry - BREAK_EVEN_BUFFER, digits)
                    if current_sl == 0 or be_sl < current_sl:
                        new_sl    = be_sl
                        stage_msg = "STAGE1_BE"

            elif current_sl <= entry or current_sl == 0:
                # --- Stage 2 ---
                if strat == "SMC" and TRAILING_SMC_REQUIRES_TP1 and current_sl > entry:
                    pass
                else:
                    trail_sl = round(price + trail_dist, digits)

                    if (current_sl == 0 or trail_sl < current_sl) \
                            and (trail_sl - price) >= min_stop:
                        new_sl    = trail_sl
                        stage_msg = "STAGE2_TRAIL"

        # ==========================================
        # MODIFY
        # ==========================================
        if new_sl is None:
            continue

        allowed, reason = demo_execution_status()
        if not allowed:
            print(f"🛑 TRAILING_ORDER_BLOCKED | {reason}")
            continue

        result = mt5.order_send({
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl":       new_sl,
            "tp":       tp
        })

        ok = result and result.retcode == mt5.TRADE_RETCODE_DONE
        print(
            f"{'✅' if ok else '❌'}"
            f" {stage_msg} | {strat} #{ticket}"
            f" SL→{new_sl}"
            f" | ATR:{atr:.2f} trail:{trail_dist:.2f} mtf:{pos_mtf_mode}"
        )
