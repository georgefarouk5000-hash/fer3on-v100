# =============================================================================
# FER3ON V3.6 — TREND CONFLUENCE ENGINE
# =============================================================================
# الفلسفة (مطابقة لفلسفة candle_gate_v3.py الموجودة مسبقًا):
#   - كل استراتيجية تحسب: خط ترند + قناة سعرية + شموع، على فريمها الخاص فقط،
#     بشكل مستقل تمامًا عن باقي الاستراتيجيات (لا حسابات مشتركة بينها).
#   - الفريم الأساسي لا يُغيَّر — كل استراتيجية تستمر على فريمها المحدد مسبقًا.
#   - المقارنة الوحيدة بين الفريمات هي: اتجاه الفريم الأساسي vs اتجاه الفريم
#     المرجعي الأعلى — ويُستخدم فقط لتحديد معامل اللوت/الوزن/نوع TP/التريلينج.
#   - التوافق (ALIGNED) يرفع الثقة واللوت. التعارض (CONFLICT) يخفضهم.
#   - التعارض لا يمنع الصفقة أبدًا — قد يكون بداية انعكاس حقيقي مبكر.
#   - Single Decision Authority يبقى Unified Decision Engine؛ هذا الموديول
#     مُنتِج أدلة إضافي (Evidence Producer) فقط — تمامًا كـ candle_gate_v3.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.candle_patterns import detect_candle_pattern_full
from core.settings import (
    TREND_CONFLUENCE_ENABLED,
    TREND_PRIMARY_TF,
    TREND_REFERENCE_TF,
    TREND_PIVOT_LOOKBACK,
    TREND_MIN_TOUCHES,
    TREND_MIN_ANGLE_DEG,
    TREND_MAX_ANGLE_DEG,
    TREND_CONFLUENCE_MAX_BONUS,
    TREND_CONFLUENCE_MAX_PENALTY,
    TREND_CONFLUENCE_BONUS_FOR,
    MTF_ALIGNED_LOT_MULT,
    MTF_NEUTRAL_LOT_MULT,
    MTF_CONFLICT_LOT_MULT,
    MTF_ALIGNED_WEIGHT_MULT,
    MTF_NEUTRAL_WEIGHT_MULT,
    MTF_CONFLICT_WEIGHT_MULT,
    MTF_ALIGNED_SCORE_BONUS,
    MTF_CONFLICT_SCORE_PENALTY,
    CANDLE_SINGLE_CONFIRM_TF,
    CANDLE_BONUS_ON_DOUBLE_TF,
    CANDLE_DOUBLE_CONFIRM_TF,
    CANDLE_DOUBLE_CONFIRM_PATTERNS,
    CANDLE_DOUBLE_CONFIRM_PARTIAL_BONUS,
    CANDLE_M5_DOUBLE_BONUS_MULT,
)


# =============================================================================
# HELPERS — قراءة الشمعة بشكل آمن (dict / numpy.void)
# =============================================================================

def _c(candle, key, default=0.0):
    try:
        if isinstance(candle, dict):
            return float(candle.get(key, default))
        if hasattr(candle, "dtype") and getattr(candle.dtype, "names", None):
            if key in candle.dtype.names:
                return float(candle[key])
        if hasattr(candle, key):
            return float(getattr(candle, key))
        return float(default)
    except Exception:
        return float(default)


def _is_bullish(candle) -> bool:
    return _c(candle, "close") > _c(candle, "open")


def _is_bearish(candle) -> bool:
    return _c(candle, "close") < _c(candle, "open")


# =============================================================================
# 1. PIVOT DETECTION — قمم وقيعان محلية (لرسم خط الترند)
# =============================================================================

def find_pivots(rates, lookback: int = 3) -> Tuple[List[int], List[int]]:
    """
    يُرجع (pivot_high_indices, pivot_low_indices) داخل rates.
    pivot high: قمة أعلى من 'lookback' شمعة على كل جانب.
    pivot low : قاع أقل من 'lookback' شمعة على كل جانب.
    """
    n = len(rates)
    highs_idx: List[int] = []
    lows_idx: List[int] = []

    if n < (lookback * 2 + 1):
        return highs_idx, lows_idx

    for i in range(lookback, n - lookback):
        window = rates[i - lookback:i + lookback + 1]
        h = _c(rates[i], "high")
        l = _c(rates[i], "low")

        if h >= max(_c(c, "high") for c in window):
            highs_idx.append(i)
        if l <= min(_c(c, "low") for c in window):
            lows_idx.append(i)

    return highs_idx, lows_idx


# =============================================================================
# 2. TREND LINE FIT — خط ترند من ≥3 لمسات (قيعان للصاعد / قمم للهابط)
# =============================================================================

def _fit_line(points: List[Tuple[int, float]]) -> Optional[Tuple[float, float]]:
    """Least-squares line fit. يُرجع (slope, intercept) أو None."""
    n = len(points)
    if n < 2:
        return None
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_xx = sum(p[0] * p[0] for p in points)
    denom = (n * sum_xx - sum_x * sum_x)
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _slope_to_angle_deg(slope: float, price_scale: float) -> float:
    """تطبيع الميل إلى زاوية تقريبية (درجات) بالنسبة لمقياس السعر."""
    import math
    if price_scale <= 0:
        return 0.0
    normalized_slope = slope / price_scale
    return abs(math.degrees(math.atan(normalized_slope)))


def detect_trend_line(rates, lookback: int = 3, min_touches: int = TREND_MIN_TOUCHES) -> Dict[str, Any]:
    """
    يحسب خط ترند صاعد (من القيعان) وخط ترند هابط (من القمم) مستقلين،
    ويُرجع الأقوى منهما حسب صلاحية الشروط (≥ min_touches + زاوية مقبولة).

    Returns dict:
        direction: BUY | SELL | NONE
        touches:   عدد اللمسات المعتبرة
        slope, intercept: معادلة الخط
        angle_deg: الزاوية التقريبية
        valid:     هل الخط صالح بالشروط
    """
    empty = {"direction": "NONE", "touches": 0, "slope": 0.0, "intercept": 0.0,
             "angle_deg": 0.0, "valid": False}

    if rates is None or len(rates) < (lookback * 2 + 5):
        return empty

    highs_idx, lows_idx = find_pivots(rates, lookback=lookback)

    price_range = max(_c(c, "high") for c in rates) - min(_c(c, "low") for c in rates)
    price_scale = max(price_range / max(len(rates), 1), 1e-9)

    candidates = []

    # خط صاعد من القيعان (uptrend support line)
    if len(lows_idx) >= min_touches:
        pts = [(i, _c(rates[i], "low")) for i in lows_idx[-6:]]  # آخر 6 لمسات كحد أقصى
        fit = _fit_line(pts)
        if fit:
            slope, intercept = fit
            angle = _slope_to_angle_deg(slope, price_scale)
            valid = (slope > 0) and (TREND_MIN_ANGLE_DEG <= angle <= TREND_MAX_ANGLE_DEG)
            candidates.append({
                "direction": "BUY", "touches": len(pts), "slope": slope,
                "intercept": intercept, "angle_deg": round(angle, 1), "valid": valid,
            })

    # خط هابط من القمم (downtrend resistance line)
    if len(highs_idx) >= min_touches:
        pts = [(i, _c(rates[i], "high")) for i in highs_idx[-6:]]
        fit = _fit_line(pts)
        if fit:
            slope, intercept = fit
            angle = _slope_to_angle_deg(slope, price_scale)
            valid = (slope < 0) and (TREND_MIN_ANGLE_DEG <= angle <= TREND_MAX_ANGLE_DEG)
            candidates.append({
                "direction": "SELL", "touches": len(pts), "slope": slope,
                "intercept": intercept, "angle_deg": round(angle, 1), "valid": valid,
            })

    valid_candidates = [c for c in candidates if c["valid"]]
    if not valid_candidates:
        return empty

    # الأقوى = أكثر لمسات؛ عند التعادل تُفضَّل الزاوية الأقرب للمنتصف (40°-50°)
    best = max(valid_candidates, key=lambda c: (c["touches"], -abs(c["angle_deg"] - 45)))
    return best


# =============================================================================
# 3. PRICE CHANNEL — خط موازٍ للترند يمر بالقمم (صاعد) أو القيعان (هابط)
# =============================================================================

def compute_price_channel(rates, trend: Dict[str, Any]) -> Dict[str, Any]:
    """
    يبني الخط الموازي لخط الترند (channel) من نفس الـ slope لكن intercept
    مأخوذ من أبعد نقطة في الاتجاه المعاكس (القمم للصاعد / القيعان للهابط).
    يُستخدم لاحقًا كمصدر بيانات لـ TP، وليس كشرط دخول.
    """
    if not trend.get("valid") or rates is None or len(rates) < 5:
        return {"valid": False}

    slope = trend["slope"]
    n = len(rates)

    if trend["direction"] == "BUY":
        # الخط الموازي العلوي يمر بأعلى قمة ضمن النافذة
        best_intercept = None
        for i, c in enumerate(rates):
            h = _c(c, "high")
            implied_intercept = h - slope * i
            if best_intercept is None or implied_intercept > best_intercept:
                best_intercept = implied_intercept
        return {"valid": True, "slope": slope, "intercept": best_intercept, "side": "upper"}

    if trend["direction"] == "SELL":
        best_intercept = None
        for i, c in enumerate(rates):
            l = _c(c, "low")
            implied_intercept = l - slope * i
            if best_intercept is None or implied_intercept < best_intercept:
                best_intercept = implied_intercept
        return {"valid": True, "slope": slope, "intercept": best_intercept, "side": "lower"}

    return {"valid": False}


def channel_target_price(channel: Dict[str, Any], index: int) -> Optional[float]:
    if not channel.get("valid"):
        return None
    return channel["slope"] * index + channel["intercept"]


# =============================================================================
# 4. CANDLE CONFIRMATION — قاعدة متغيرة حسب سرعة الفريم
# =============================================================================

def evaluate_candle_confirmation(rates, tf_name: str) -> Dict[str, Any]:
    """
    يطبّق قاعدة التأكيد المناسبة لسرعة الفريم:
      - M1            : شمعة واحدة كافية (لا قاعدة شمعتين — يفوّت التوقيت)
      - M5            : شمعة واحدة + بونص لو شمعتين متتاليتين متوافقتين
      - M15/H1/H4/D1/W1: شمعتين تأكيد إلزامي لأنماط الشمعة الواحدة فقط
                         (Tier A مثل Engulfing/3-Soldiers مُستثناة، متعددة الشموع أصلاً)
    """
    pattern_name, direction, weight = detect_candle_pattern_full(rates)

    result = {
        "pattern": pattern_name, "direction": direction, "weight": weight,
        "confirmed": direction != "NONE", "bonus_mult": 1.0, "note": "",
    }

    if direction == "NONE":
        return result

    tf = str(tf_name or "").upper()

    # --- M1: شمعة واحدة كافية، بلا أي تخفيف ---
    if tf in CANDLE_SINGLE_CONFIRM_TF:
        result["note"] = "SINGLE_CONFIRM_M1"
        return result

    # --- M5: شمعة واحدة + بونص اختياري لو شمعتين متتاليتين بنفس الانحياز ---
    if tf in CANDLE_BONUS_ON_DOUBLE_TF:
        if len(rates) >= 2:
            prev, last = rates[-2], rates[-1]
            same_bias = (
                (direction == "BUY" and _is_bullish(prev) and _is_bullish(last))
                or (direction == "SELL" and _is_bearish(prev) and _is_bearish(last))
            )
            if same_bias:
                result["bonus_mult"] = CANDLE_M5_DOUBLE_BONUS_MULT
                result["note"] = "DOUBLE_CANDLE_BONUS_M5"
            else:
                result["note"] = "SINGLE_CANDLE_M5"
        return result

    # --- M15+ : شمعتين تأكيد إلزامي لأنماط الشمعة الواحدة فقط ---
    if tf in CANDLE_DOUBLE_CONFIRM_TF:
        if pattern_name.upper() in CANDLE_DOUBLE_CONFIRM_PATTERNS:
            if len(rates) >= 2:
                prev = rates[-2]
                same_bias = (
                    (direction == "BUY" and _is_bullish(prev))
                    or (direction == "SELL" and _is_bearish(prev))
                )
                if same_bias:
                    result["note"] = f"DOUBLE_CONFIRMED_{tf}"
                else:
                    # تخفيف لا حظر — نفس فلسفة المشروع المعلنة
                    result["bonus_mult"] = CANDLE_DOUBLE_CONFIRM_PARTIAL_BONUS
                    result["note"] = f"PARTIAL_NO_SECOND_CONFIRM_{tf}"
            else:
                result["bonus_mult"] = CANDLE_DOUBLE_CONFIRM_PARTIAL_BONUS
                result["note"] = "INSUFFICIENT_DATA"
        else:
            # نمط متعدد الشموع أصلاً (Tier A) — لا حاجة لتأكيد إضافي
            result["note"] = f"MULTI_CANDLE_PATTERN_{tf}"

    return result


# =============================================================================
# 5. PER-TIMEFRAME TREND CONFLUENCE — الدالة الموحّدة لكل فريم
# =============================================================================

def analyze_timeframe_confluence(rates, tf_name: str) -> Dict[str, Any]:
    """
    يحسب ترند + قناة + شموع لفريم واحد بشكل مستقل بالكامل.
    يُستخدم لكل من الفريم الأساسي والفريم المرجعي لكل استراتيجية.
    """
    if not TREND_CONFLUENCE_ENABLED or rates is None:
        return {
            "tf": tf_name, "trend_direction": "NONE", "trend_valid": False,
            "candle_direction": "NONE", "final_direction": "NONE",
        }

    lookback = TREND_PIVOT_LOOKBACK.get(str(tf_name).upper(), 3)
    trend = detect_trend_line(rates, lookback=lookback)
    channel = compute_price_channel(rates, trend)
    candle = evaluate_candle_confirmation(rates, tf_name)

    # اتجاه نهائي للفريم = ترند صالح إن وُجد، وإلا اتجاه الشموع كبديل
    if trend.get("valid"):
        final_direction = trend["direction"]
    else:
        final_direction = candle.get("direction", "NONE")

    return {
        "tf": tf_name,
        "trend_direction": trend.get("direction", "NONE"),
        "trend_valid": trend.get("valid", False),
        "trend_touches": trend.get("touches", 0),
        "trend_angle_deg": trend.get("angle_deg", 0.0),
        "channel": channel,
        "candle_pattern": candle.get("pattern", "NONE"),
        "candle_direction": candle.get("direction", "NONE"),
        "candle_weight": candle.get("weight", 0),
        "candle_bonus_mult": candle.get("bonus_mult", 1.0),
        "candle_note": candle.get("note", ""),
        "final_direction": final_direction,
    }


# =============================================================================
# 6. MTF ALIGNMENT — مقارنة الفريم الأساسي بالفريم المرجعي الأعلى فقط
# =============================================================================

def evaluate_mtf_alignment(local_direction: str, higher_direction: str) -> Dict[str, Any]:
    """
    يُرجع: alignment_mode + معاملات اللوت/الوزن/سكور.
    القاعدة المتفقة:
      - الفريم الأعلى يفوز دائمًا في تحديد "الحالة" (aligned/conflict)،
        لكنه لا يمنع الصفقة أبدًا — فقط يُحجّم حجمها وثقتها.
    """
    local = str(local_direction or "NONE").upper()
    higher = str(higher_direction or "NONE").upper()

    if local == "NONE" or higher == "NONE":
        mode = "NEUTRAL"
        lot_mult = MTF_NEUTRAL_LOT_MULT
        weight_mult = MTF_NEUTRAL_WEIGHT_MULT
        score_delta = 0.0
    elif local == higher:
        mode = "ALIGNED"
        lot_mult = MTF_ALIGNED_LOT_MULT
        weight_mult = MTF_ALIGNED_WEIGHT_MULT
        score_delta = MTF_ALIGNED_SCORE_BONUS
    else:
        mode = "CONFLICT"
        lot_mult = MTF_CONFLICT_LOT_MULT
        weight_mult = MTF_CONFLICT_WEIGHT_MULT
        score_delta = MTF_CONFLICT_SCORE_PENALTY

    return {
        "mode": mode,
        "lot_multiplier": lot_mult,
        "weight_multiplier": weight_mult,
        "score_delta": score_delta,
        "local_direction": local,
        "higher_direction": higher,
        "blocked": False,  # دائمًا False — التعارض لا يمنع الصفقة أبدًا
    }


# =============================================================================
# 7. MAIN ENTRY POINT — يُستدعى من كل استراتيجية بفريميها
# =============================================================================

def evaluate_trend_confluence(
    strategy: str,
    primary_rates,
    reference_rates,
    signal: str,
) -> Dict[str, Any]:
    """
    الدالة الرئيسية: تُستدعى من كل استراتيجية مع بيانات فريمها الأساسي
    وفريمها المرجعي، وتُرجع كل المخرجات اللازمة لـ unified_decision +
    adaptive_lot_engine + multi_tp + trailing.

    Parameters
    ----------
    strategy        : "SMC" | "DAILY"
    primary_rates   : شموع الفريم الأساسي للاستراتيجية
    reference_rates : شموع الفريم المرجعي الأعلى
    signal          : "BUY" | "SELL" (اتجاه الصفقة المرشحة من محرك الاستراتيجية)
    """
    strat = str(strategy or "").upper()
    primary_tf = TREND_PRIMARY_TF.get(strat, "M5")
    reference_tf = TREND_REFERENCE_TF.get(strat, "H1")

    primary = analyze_timeframe_confluence(primary_rates, primary_tf)
    reference = analyze_timeframe_confluence(reference_rates, reference_tf)

    alignment = evaluate_mtf_alignment(
        primary["final_direction"], reference["final_direction"]
    )

    # بونص/عقوبة الترند الإضافي (محدود ومضبوط بسقف) — لـ DAILY/SMC فقط حسب الاتفاق
    trend_bonus = 0.0
    trend_penalty = 0.0
    if strat in TREND_CONFLUENCE_BONUS_FOR and primary.get("trend_valid"):
        sig = str(signal or "").upper()
        if primary["trend_direction"] == sig:
            touches_factor = min(primary.get("trend_touches", 0) / 5.0, 1.0)
            trend_bonus = round(TREND_CONFLUENCE_MAX_BONUS * touches_factor, 2)
        elif primary["trend_direction"] not in ("NONE", sig):
            trend_penalty = round(TREND_CONFLUENCE_MAX_PENALTY * 0.6, 2)

    log_line = (
        f"📈 TREND_CONFLUENCE | Strategy:{strat}"
        f" | Primary({primary_tf}):{primary['final_direction']}"
        f" (trend_valid={primary['trend_valid']}, touches={primary.get('trend_touches', 0)})"
        f" | Reference({reference_tf}):{reference['final_direction']}"
        f" | Mode:{alignment['mode']}"
        f" | LotMult:{alignment['lot_multiplier']:.2f}"
        f" | WeightMult:{alignment['weight_multiplier']:.2f}"
        f" | TrendBonus:{trend_bonus:+.1f} TrendPenalty:{-trend_penalty:+.1f}"
    )
    print(log_line)

    return {
        "strategy": strat,
        "primary": primary,
        "reference": reference,
        "alignment": alignment,
        "trend_bonus": trend_bonus,
        "trend_penalty": trend_penalty,
        "log_line": log_line,
    }
