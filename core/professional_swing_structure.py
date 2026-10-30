from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _get_rate_field(rate: Any, field: str, default: float = 0.0) -> float:
    if rate is None:
        return float(default)
    try:
        if isinstance(rate, dict):
            return float(rate.get(field, default) or default)
        if hasattr(rate, field):
            return float(getattr(rate, field) or default)
        if hasattr(rate, 'dtype') and getattr(rate, 'dtype', None) is not None:
            if field in getattr(rate.dtype, 'names', ()):
                return float(rate[field] or default)
        try:
            return float(rate[field] or default)
        except Exception:
            return float(default)
    except Exception:
        return float(default)


def _range(candle: Dict[str, Any]) -> float:
    return max(_get_rate_field(candle, "high") - _get_rate_field(candle, "low"), 0.0)


def _swing_points(rates: List[Dict[str, Any]], left: int = 3, right: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    highs: List[Tuple[int, float]] = []
    lows: List[Tuple[int, float]] = []
    n = len(rates)
    for idx in range(left, n - right):
        candle = rates[idx]
        if all(_get_rate_field(rates[idx - k], "high") <= _get_rate_field(candle, "high") for k in range(1, left + 1)) and all(_get_rate_field(rates[idx + k], "high") <= _get_rate_field(candle, "high") for k in range(1, right + 1)):
            highs.append((idx, _get_rate_field(candle, "high")))
        if all(_get_rate_field(rates[idx - k], "low") >= _get_rate_field(candle, "low") for k in range(1, left + 1)) and all(_get_rate_field(rates[idx + k], "low") >= _get_rate_field(candle, "low") for k in range(1, right + 1)):
            lows.append((idx, _get_rate_field(candle, "low")))
    return highs, lows


def _label_swing_points(
    points: List[Tuple[int, float]],
    *,
    high: bool,
) -> List[Dict[str, Any]]:
    labeled: List[Dict[str, Any]] = []
    previous_price: Optional[float] = None
    for index, price in points:
        if previous_price is None:
            label = "INITIAL_HIGH" if high else "INITIAL_LOW"
        elif price > previous_price:
            label = "HH" if high else "HL"
        elif price < previous_price:
            label = "LH" if high else "LL"
        else:
            label = "EQH" if high else "EQL"
        labeled.append({"index": index, "price": price, "label": label})
        previous_price = price
    return labeled


def _protected_swing(
    swing_highs: List[Dict[str, Any]],
    swing_lows: List[Dict[str, Any]],
    bias: str,
) -> Dict[str, Any]:
    if bias == "BUY" and swing_lows and swing_lows[-1]["label"] == "HL":
        return {
            **swing_lows[-1],
            "kind": "protected_low",
            "reason": "LAST_CONFIRMED_HIGHER_LOW",
        }
    if bias == "SELL" and swing_highs and swing_highs[-1]["label"] == "LH":
        return {
            **swing_highs[-1],
            "kind": "protected_high",
            "reason": "LAST_CONFIRMED_LOWER_HIGH",
        }
    return {}


def _detect_bos(rates: List[Dict[str, Any]]) -> Tuple[str, float, bool]:
    """
    [FER3ON-FIX-2026-09-02] BOS اكتشاف معادل
    المشكلة الأصلية: كان يكتشف DOWN أكثر من UP
    السبب: الشرط كان متحيزاً في حساب structure_high/structure_low
    الحل: موازنة النسبة المئوية المستخدمة (70% → 50% محايد)
    """
    if rates is None or len(rates) < 10:
        return "NONE", 0.0, False
    
    recent = rates[-20:]
    highs = [_get_rate_field(c, "high") for c in recent]
    lows = [_get_rate_field(c, "low") for c in recent]
    
    # السابق: split = 70% (متحيز)
    # ✅ FIX [2026-09-02]: split = 50% (محايد تماماً)
    split = max(3, int(len(recent) * 0.5))
    
    structure_high = max(highs[:split]) if highs else 0.0
    structure_low = min(lows[:split]) if lows else 0.0
    close = _get_rate_field(recent[-1], "close")
    
    # شروط متساوية
    bos_up = close > structure_high and _get_rate_field(recent[-1], "high") > structure_high
    bos_down = close < structure_low and _get_rate_field(recent[-1], "low") < structure_low
    
    if bos_up and bos_down:
        # كلاهما صحيح — لا نقرر
        return "NONE", 0.0, False
    
    if bos_up:
        return "BOS_UP", structure_high, True
    if bos_down:
        return "BOS_DOWN", structure_low, True
    
    return "NONE", 0.0, False


def _detect_choch(rates: List[Dict[str, Any]]) -> Tuple[str, float, str]:
    """
    [FER3ON-FIX-2026-09-02] CHOCH اكتشاف معادل
    المشكلة الأصلية: كان يكتشف BEARISH 4x أكثر من BULLISH
    السبب: الشرط الأصلي كان غير متوازن (highs صاعدة ← BEARISH غريب)
    الحل: موازنة الشروط + عكس معاملات التقييم
    """
    if rates is None or len(rates) < 12:
        return "NONE", 0.0, "WEAK"
    highs = [_get_rate_field(c, "high") for c in rates[-12:]]
    lows = [_get_rate_field(c, "low") for c in rates[-12:]]
    if len(highs) < 4 or len(lows) < 4:
        return "NONE", 0.0, "WEAK"
    
    # تحقق من Bearish Reversal (آخر 3 قيم)
    bearish_reversal = (
        highs[-1] > highs[-2] and highs[-2] > highs[-3] and  # highs صاعدة
        lows[-1] < lows[-2] and lows[-2] < lows[-3]          # lows هابطة (عكس)
    )
    
    # تحقق من Bullish Reversal (آخر 3 قيم)
    bullish_reversal = (
        highs[-1] < highs[-2] and highs[-2] < highs[-3] and  # highs هابطة (عكس)
        lows[-1] > lows[-2] and lows[-2] > lows[-3]          # lows صاعدة
    )
    
    # الحل: إذا كانت كلاهما موجودة، قيّم قوة كل واحدة بشكل محايد
    if bearish_reversal and bullish_reversal:
        # كلاهما موجود — قيم أيهما أقوى
        # لا تعطي الأولوية تلقائياً لأحدهما
        return "NONE", 0.0, "WEAK"
    
    if bearish_reversal:
        return "CHOCH_BEARISH", lows[-2], "STRONG"
    if bullish_reversal:
        return "CHOCH_BULLISH", highs[-2], "STRONG"  # كانت "MODERATE" — الآن "STRONG"
    
    return "NONE", 0.0, "WEAK"


def _equal_levels(rates: List[Dict[str, Any]], tolerance: float = 3.0) -> Dict[str, List[float]]:
    highs = [_get_rate_field(c, "high") for c in rates[-20:]]
    lows = [_get_rate_field(c, "low") for c in rates[-20:]]
    return {
        "equal_highs": _cluster_levels(highs, tolerance),
        "equal_lows": _cluster_levels(lows, tolerance),
    }


def _cluster_levels(values: List[float], tolerance: float) -> List[float]:
    zones: List[float] = []
    for idx, value in enumerate(values):
        cluster = [value]
        for other in values[idx + 1:]:
            if abs(other - value) <= tolerance:
                cluster.append(other)
        if len(cluster) >= 2:
            zones.append(round(sum(cluster) / len(cluster), 2))
    return zones


def analyze_swing_structure(rates: List[Dict[str, Any]], current_price: Optional[float] = None) -> Dict[str, Any]:
    if rates is None or len(rates) == 0:
        return {
            "structure_bias": "NEUTRAL",
            "structure_strength": 0.0,
            "swing_high": 0.0,
            "swing_low": 0.0,
            "swing_highs": [],
            "swing_lows": [],
            "protected_high": {},
            "protected_low": {},
            "bos": "NONE",
            "choch": "NONE",
            "equal_highs": [],
            "equal_lows": [],
            "liquidity_zone": 0.0,
            "premium_discount": "NEUTRAL",
        }

    highs, lows = _swing_points(rates)
    swing_highs = _label_swing_points(highs, high=True)
    swing_lows = _label_swing_points(lows, high=False)
    if highs and lows:
        swing_high = max(price for _, price in highs[-3:])
        swing_low = min(price for _, price in lows[-3:])
    else:
        swing_high = max(_get_rate_field(c, "high") for c in rates)
        swing_low = min(_get_rate_field(c, "low") for c in rates)

    if current_price is None:
        current_price = _get_rate_field(rates[-1], "close")

    bos, bos_level, bos_confirmed = _detect_bos(rates)
    choch, choch_level, choch_strength = _detect_choch(rates)
    equal_levels = _equal_levels(rates)

    if bos == "BOS_UP" or choch == "CHOCH_BULLISH":
        bias = "BUY"
    elif bos == "BOS_DOWN" or choch == "CHOCH_BEARISH":
        bias = "SELL"
    else:
        bias = "NEUTRAL"
    protected_swing = _protected_swing(swing_highs, swing_lows, bias)

    if current_price > swing_low and current_price < swing_high:
        strength = 55.0 + min(abs(current_price - ((swing_high + swing_low) / 2.0)) / max(swing_high - swing_low, 1e-9) * 35.0, 35.0)
    else:
        strength = 62.0

    if bos_confirmed:
        strength += 12.0
    if choch_strength == "STRONG":
        strength += 10.0
    if bias == "BUY" and current_price > ((swing_high + swing_low) / 2.0):
        strength += 6.0
    if bias == "SELL" and current_price < ((swing_high + swing_low) / 2.0):
        strength += 6.0

    strength = min(100.0, max(0.0, strength))

    entry_reason_parts: List[str] = []
    if choch != "NONE":
        entry_reason_parts.append("CHOCH")
    if bos != "NONE":
        entry_reason_parts.append("BOS")
    if equal_levels["equal_highs"] or equal_levels["equal_lows"]:
        entry_reason_parts.append("EQUAL_LEVEL")
    if abs(current_price - ((swing_high + swing_low) / 2.0)) > 0:
        entry_reason_parts.append("LIQUIDITY")

    return {
        "structure_bias": bias,
        "structure_strength": round(strength, 2),
        "swing_high": round(swing_high, 2),
        "swing_low": round(swing_low, 2),
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "last_swing_high": swing_highs[-1]["price"] if swing_highs else None,
        "last_swing_low": swing_lows[-1]["price"] if swing_lows else None,
        "protected_high": (
            protected_swing if protected_swing.get("kind") == "protected_high" else {}
        ),
        "protected_low": (
            protected_swing if protected_swing.get("kind") == "protected_low" else {}
        ),
        "bos": bos,
        "choch": choch,
        "equal_highs": equal_levels["equal_highs"],
        "equal_lows": equal_levels["equal_lows"],
        "liquidity_zone": round((swing_high + swing_low) / 2.0, 2),
        "premium_discount": "DISCOUNT" if current_price < ((swing_high + swing_low) / 2.0) else "PREMIUM",
        "bos_level": bos_level,
        "choch_level": choch_level,
        "choch_strength": choch_strength,
        "entry_reason": " | ".join(entry_reason_parts) if entry_reason_parts else "STRUCTURE",
        "entry_reason_parts": entry_reason_parts,
    }


def evaluate_entry_readiness(analysis: Dict[str, Any], entry_price: Optional[float] = None) -> Dict[str, Any]:
    if not analysis:
        return {"ready": False, "reasons": ["NO_STRUCTURE"], "score": 0.0}

    entry_value = _coerce_float(entry_price, 0.0)
    reasons: List[str] = []
    score = _coerce_float(analysis.get("structure_strength", 0.0), 0.0)

    if str(analysis.get("bos", "NONE")).upper() != "NONE":
        reasons.append("BOS")
        score += 12.0
    if str(analysis.get("choch", "NONE")).upper() != "NONE":
        reasons.append("CHOCH")
        score += 12.0
    if entry_value > 0:
        swing_low = _coerce_float(analysis.get("swing_low", 0.0), 0.0)
        swing_high = _coerce_float(analysis.get("swing_high", 0.0), 0.0)
        if entry_value > swing_low and entry_value < swing_high:
            reasons.append("STRUCTURE_RANGE")
            score += 4.0
        if abs(entry_value - swing_low) > 0 and abs(entry_value - swing_high) > 0:
            reasons.append("LIQUIDITY")
            score += 4.0

    ready = score >= 65.0 and len(reasons) >= 2
    return {"ready": ready, "reasons": reasons, "score": round(score, 2)}


def select_structural_targets(analysis: Dict[str, Any], entry_price: Optional[float] = None, signal: Optional[str] = None) -> Dict[str, Any]:
    entry_value = _coerce_float(entry_price, 0.0)
    bias = str(signal or analysis.get("structure_bias", "NEUTRAL") or "NEUTRAL").upper()
    targets: List[Dict[str, Any]] = []
    if entry_value <= 0 or bias not in {"BUY", "SELL"}:
        return {
            "targets": [],
            "best_target": {"name": "None", "price": entry_value, "distance": 0.0, "type": "none"},
        }

    swing_high = _coerce_float(analysis.get("swing_high", 0.0), 0.0)
    swing_low = _coerce_float(analysis.get("swing_low", 0.0), 0.0)
    liquidity_zone = _coerce_float(analysis.get("liquidity_zone", 0.0), 0.0)
    equal_highs = analysis.get("equal_highs") or []
    equal_lows = analysis.get("equal_lows") or []

    if bias == "BUY":
        high_levels = [
            _coerce_float(level.get("price"), 0.0) if isinstance(level, dict)
            else _coerce_float(level, 0.0)
            for level in analysis.get("swing_highs", []) or []
        ]
        high_levels.append(swing_high)
        for level in high_levels:
            if level > entry_value:
                targets.append({"name": "Swing High", "price": level, "distance": level - entry_value, "type": "swing"})
        if equal_highs:
            for level in equal_highs:
                if level > entry_value:
                    targets.append({"name": "Equal High", "price": level, "distance": abs(level - entry_value), "type": "equal_high"})
        if liquidity_zone > entry_value:
            targets.append({"name": "Liquidity Zone", "price": liquidity_zone, "distance": abs(liquidity_zone - entry_value), "type": "liquidity"})
    else:
        low_levels = [
            _coerce_float(level.get("price"), 0.0) if isinstance(level, dict)
            else _coerce_float(level, 0.0)
            for level in analysis.get("swing_lows", []) or []
        ]
        low_levels.append(swing_low)
        for level in low_levels:
            if 0 < level < entry_value:
                targets.append({"name": "Swing Low", "price": level, "distance": entry_value - level, "type": "swing"})
        if equal_lows:
            for level in equal_lows:
                if 0 < level < entry_value:
                    targets.append({"name": "Equal Low", "price": level, "distance": abs(entry_value - level), "type": "equal_low"})
        if liquidity_zone < entry_value:
            targets.append({"name": "Liquidity Zone", "price": liquidity_zone, "distance": abs(entry_value - liquidity_zone), "type": "liquidity"})

    unique_targets = {
        (round(float(item["price"]), 5), item["type"]): item
        for item in targets
        if float(item["distance"]) > 0
    }
    targets = sorted(unique_targets.values(), key=lambda item: item["distance"])
    best_target = targets[0] if targets else {"name": "None", "price": entry_value, "distance": 0.0, "type": "none"}
    return {"targets": targets, "best_target": best_target}


def build_swing_structure_report(
    analysis: Dict[str, Any],
    entry_price: Optional[float] = None,
    signal: Optional[str] = None,
    stop_distance: Optional[float] = None,
    tp_distance: Optional[float] = None,
    final_rr: Optional[float] = None,
    stop_source: Optional[str] = None,
    stop_anchor: Optional[Dict[str, Any]] = None,
    stop_reason: Optional[str] = None,
    stop_buffer: Optional[float] = None,
    target_source: Optional[str] = None,
    target_price: Optional[float] = None,
) -> str:
    bias = str(signal or analysis.get("structure_bias", "NEUTRAL") or "NEUTRAL").upper()
    trend = "Bullish" if bias == "BUY" else "Bearish" if bias == "SELL" else "Neutral"
    entry_value = _coerce_float(entry_price, 0.0)
    strength = _coerce_float(analysis.get("structure_strength", 0.0), 0.0)
    entry_reason = str(analysis.get("entry_reason", "STRUCTURE"))
    anchor = stop_anchor or {}
    anchor_price = anchor.get("price")
    anchor_label = str(anchor.get("label") or anchor.get("kind") or "UNLABELED")
    anchor_index = anchor.get("index")
    anchor_detail = (
        f"{anchor_label} @ {float(anchor_price):.5f} (index={anchor_index})"
        if anchor_price is not None
        else "N/A"
    )
    lines = [
        "SWING STRUCTURE REPORT",
        f"Primary Trend : {trend}",
        f"Entry Swing : {'Strong' if strength >= 70 else 'Moderate' if strength >= 50 else 'Weak'}",
        f"Swing Strength : {strength:.0f}",
        "Entry Reason :",
        entry_reason,
        "Stop Source :",
        str(stop_source or "ATR"),
        "Stop Anchor :",
        anchor_detail,
        "Stop Selection Reason :",
        str(stop_reason or "ATR_FALLBACK"),
        "ATR Buffer :",
        f"{stop_buffer:.5f}" if stop_buffer is not None else "N/A",
        "Stop Distance :",
        f"{stop_distance:.1f}" if stop_distance is not None else "N/A",
        "Target Source :",
        str(target_source or "RR_FALLBACK"),
        "Target Price :",
        f"{target_price:.5f}" if target_price is not None else "N/A",
        "Target Distance :",
        f"{tp_distance:.1f}" if tp_distance is not None else "N/A",
        "Final RR :",
        f"{final_rr:.2f}" if final_rr is not None else "N/A",
        "Decision :",
        "TARGET AVAILABLE" if target_price is not None and entry_value > 0 else "RR FALLBACK",
    ]
    return "\n".join(lines)
