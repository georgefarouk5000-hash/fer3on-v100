# =========================================
# FER3ON — ANCHORED VWAP (REAL)
# =========================================
# تحسب Volume-Weighted Average Price الحقيقي بدءًا من "مرساة" (anchor):
#   - session_open : بداية جلسة (Asia/London/NY حسب ساعة UTC)
#   - day_open     : بداية اليوم UTC
#   - swing_high   : أعلى قمة خلال lookback
#   - swing_low    : أدنى قاع خلال lookback
#   - index        : مرساة يدوية عبر index مباشر
#
# الحساب:
#   typical_price_i = (high_i + low_i + close_i) / 3
#   VWAP_t = Σ(TP_i * V_i) / Σ(V_i)    for i from anchor .. t
#
# مصدر الحجم:
#   real_volume إن توفر، وإلا tick_volume، وإلا وزن = 1 (uniform / time-based VWAP)
#   يُصرَّح بذلك في المفتاح "source" ضمن الناتج.
#
# الملاحظة المضلّلة القديمة (detect_vwap_reclaim_candle في core/candle_patterns.py)
# لم تكن تحسب VWAP فعلًا — كانت midpoint reclaim فقط. صُحِّحت التسمية في
# core/candle_patterns.py إلى detect_midpoint_reclaim_candle، وبعد فترة
# انتقالية أُزيل الـ alias القديم بالكامل (لم يعد أي كود إنتاجي يعتمد
# عليه). الحساب الحقيقي هنا.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# -----------------------------
# مساعدات
# -----------------------------

def _cf(rate: Any, key: str, default: float = 0.0) -> float:
    try:
        if isinstance(rate, dict):
            v = rate.get(key, default)
        else:
            v = getattr(rate, key, default)
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _ci(rate: Any, key: str, default: int = 0) -> int:
    try:
        if isinstance(rate, dict):
            v = rate.get(key, default)
        else:
            v = getattr(rate, key, default)
        if v is None:
            return int(default)
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def _candle_weight(rate: Any) -> tuple[float, str]:
    """(weight, source_type)"""
    real_v = _cf(rate, "real_volume", 0.0)
    if real_v > 0:
        return real_v, "real_volume"
    tick_v = _cf(rate, "tick_volume", 0.0)
    if tick_v > 0:
        return tick_v, "tick_volume"
    v = _cf(rate, "volume", 0.0)
    if v > 0:
        return v, "tick_volume"
    return 1.0, "uniform"


def _typical(rate: Any) -> float:
    h = _cf(rate, "high", 0.0)
    l = _cf(rate, "low", 0.0)
    c = _cf(rate, "close", 0.0)
    if h <= 0 or l <= 0 or c <= 0:
        return 0.0
    return (h + l + c) / 3.0


# -----------------------------
# اختيار المرساة
# -----------------------------

def _anchor_index_session(rates: List[Any]) -> int:
    """أول شمعة داخل الجلسة الحالية (UTC hour block)."""
    if not rates:
        return 0
    now_hour = datetime.now(timezone.utc).hour
    # session blocks: Asia 0-7, London 8-12, NewYork 13-20, Late 21-23
    if 0 <= now_hour < 8:
        block = (0, 8)
    elif 8 <= now_hour < 13:
        block = (8, 13)
    elif 13 <= now_hour < 21:
        block = (13, 21)
    else:
        block = (21, 24)

    anchor = 0
    for i, r in enumerate(rates):
        t = _ci(r, "time", 0)
        if t <= 0:
            continue
        try:
            dt = datetime.fromtimestamp(t, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            continue
        if block[0] <= dt.hour < block[1]:
            anchor = i
            break
    return anchor


def _anchor_index_day(rates: List[Any]) -> int:
    """أول شمعة في اليوم الحالي UTC."""
    if not rates:
        return 0
    today = datetime.now(timezone.utc).date()
    for i, r in enumerate(rates):
        t = _ci(r, "time", 0)
        if t <= 0:
            continue
        try:
            dt = datetime.fromtimestamp(t, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            continue
        if dt.date() == today:
            return i
    return 0


def _anchor_index_swing(rates: List[Any], lookback: int, kind: str) -> int:
    if not rates:
        return 0
    window = rates[-max(2, int(lookback)):]
    start = len(rates) - len(window)
    if kind == "swing_high":
        best_i = max(range(len(window)), key=lambda i: _cf(window[i], "high", 0.0))
    else:
        # swing_low
        vals = [_cf(w, "low", 0.0) for w in window]
        # نتجاهل الأصفار حتى لا نختار شمعة فاسدة
        valid_indices = [i for i in range(len(window)) if vals[i] > 0]
        if not valid_indices:
            return 0
        best_i = min(valid_indices, key=lambda i: vals[i])
    return start + best_i


def resolve_anchor(
    rates: List[Any],
    anchor: str = "session_open",
    lookback: int = 60,
    index: Optional[int] = None,
) -> int:
    """يُرجع فهرس البداية للمرساة داخل rates."""
    if not rates:
        return 0
    anchor = (anchor or "session_open").lower()
    if anchor == "index" and index is not None:
        return max(0, min(int(index), len(rates) - 1))
    if anchor == "day_open":
        return _anchor_index_day(rates)
    if anchor == "swing_high":
        return _anchor_index_swing(rates, lookback, "swing_high")
    if anchor == "swing_low":
        return _anchor_index_swing(rates, lookback, "swing_low")
    # default
    return _anchor_index_session(rates)


# -----------------------------
# الحساب الأساسي
# -----------------------------

def compute_anchored_vwap(
    rates: List[Any],
    anchor: str = "session_open",
    lookback: int = 60,
    index: Optional[int] = None,
    include_bands: bool = True,
) -> Dict[str, Any]:
    """
    Anchored VWAP الحقيقي.

    يُعيد:
      valid, anchor, anchor_index, vwap (آخر قيمة),
      series (قائمة VWAP لكل شمعة من المرساة إلى النهاية),
      upper_band_1sd, lower_band_1sd, upper_band_2sd, lower_band_2sd,
      distance_from_price (السعر الحالي − VWAP),
      source (real_volume|tick_volume|uniform|mixed)
    """
    if not rates or len(rates) < 2:
        return _empty_vwap("insufficient_rates", anchor)

    anchor_idx = resolve_anchor(rates, anchor=anchor, lookback=lookback, index=index)
    segment = rates[anchor_idx:]
    if len(segment) < 2:
        return _empty_vwap("segment_too_short", anchor)

    cum_vp = 0.0
    cum_v = 0.0
    cum_vp2 = 0.0  # Σ(TP^2 * V) لحساب الانحراف المعياري المرجّح
    series: List[float] = []
    variances: List[float] = []
    sources_seen: dict[str, int] = {}

    for r in segment:
        tp = _typical(r)
        if tp <= 0:
            # نُضيف NaN-like: نُبقي آخر VWAP معروف بدل الكسر
            series.append(series[-1] if series else 0.0)
            variances.append(variances[-1] if variances else 0.0)
            continue
        w, wtype = _candle_weight(r)
        sources_seen[wtype] = sources_seen.get(wtype, 0) + 1
        cum_vp += tp * w
        cum_vp2 += (tp * tp) * w
        cum_v += w
        if cum_v > 0:
            v = cum_vp / cum_v
            series.append(v)
            # variance = E[X^2] - (E[X])^2 مرجّحًا بالحجم
            e_x2 = cum_vp2 / cum_v
            var = max(0.0, e_x2 - v * v)
            variances.append(var)
        else:
            series.append(0.0)
            variances.append(0.0)

    if cum_v <= 0 or not series:
        return _empty_vwap("zero_cumulative_volume", anchor)

    vwap_now = series[-1]
    var_now = variances[-1]
    sd = var_now ** 0.5

    last_close = _cf(segment[-1], "close", 0.0)
    if len(sources_seen) == 1:
        source = next(iter(sources_seen))
    elif len(sources_seen) > 1:
        source = "mixed"
    else:
        source = "uniform"

    out: Dict[str, Any] = {
        "valid": True,
        "anchor": anchor,
        "anchor_index": anchor_idx,
        "vwap": vwap_now,
        "series": series,
        "distance_from_price": last_close - vwap_now if last_close > 0 else 0.0,
        "price": last_close,
        "source": source,
        "sources_breakdown": sources_seen,
        "sample_size": len(segment),
    }
    if include_bands:
        out["upper_band_1sd"] = vwap_now + sd
        out["lower_band_1sd"] = vwap_now - sd
        out["upper_band_2sd"] = vwap_now + 2.0 * sd
        out["lower_band_2sd"] = vwap_now - 2.0 * sd
        out["stdev"] = sd
    return out


def _empty_vwap(reason: str, anchor: str) -> Dict[str, Any]:
    return {
        "valid": False,
        "reason": reason,
        "anchor": anchor,
        "anchor_index": 0,
        "vwap": 0.0,
        "series": [],
        "upper_band_1sd": 0.0,
        "lower_band_1sd": 0.0,
        "upper_band_2sd": 0.0,
        "lower_band_2sd": 0.0,
        "stdev": 0.0,
        "distance_from_price": 0.0,
        "price": 0.0,
        "source": "none",
        "sources_breakdown": {},
        "sample_size": 0,
    }


# -----------------------------
# استنتاجات جاهزة
# -----------------------------

def vwap_bias(vwap_result: Dict[str, Any]) -> str:
    """BUY / SELL / NEUTRAL حسب موقع السعر من VWAP وحدوده."""
    if not vwap_result or not vwap_result.get("valid"):
        return "NEUTRAL"
    price = float(vwap_result.get("price", 0.0))
    vwap = float(vwap_result.get("vwap", 0.0))
    if price <= 0 or vwap <= 0:
        return "NEUTRAL"
    upper1 = float(vwap_result.get("upper_band_1sd", vwap))
    lower1 = float(vwap_result.get("lower_band_1sd", vwap))
    if price >= upper1:
        return "BUY"
    if price <= lower1:
        return "SELL"
    if price > vwap:
        return "BUY"
    if price < vwap:
        return "SELL"
    return "NEUTRAL"


def vwap_reclaim_signal(rates: List[Any], vwap_result: Dict[str, Any]) -> str:
    """
    إشارة استعادة VWAP الحقيقية:
      BUY  إذا فتحت آخر شمعة أسفل VWAP وأغلقت فوقه بجسم قوي.
      SELL إذا فتحت فوقه وأغلقت تحته بجسم قوي.
      NONE خلاف ذلك.
    """
    if not rates or len(rates) < 2:
        return "NONE"
    if not vwap_result or not vwap_result.get("valid"):
        return "NONE"
    series = vwap_result.get("series") or []
    if len(series) < 2:
        return "NONE"
    last = rates[-1]
    open_p = _cf(last, "open", 0.0)
    close_p = _cf(last, "close", 0.0)
    high_p = _cf(last, "high", 0.0)
    low_p = _cf(last, "low", 0.0)
    vwap_last = float(series[-1])
    if open_p <= 0 or close_p <= 0 or vwap_last <= 0:
        return "NONE"
    body = abs(close_p - open_p)
    rng = max(1e-9, high_p - low_p)
    body_ratio = body / rng
    if body_ratio < 0.4:
        return "NONE"
    if open_p < vwap_last and close_p > vwap_last:
        return "BUY"
    if open_p > vwap_last and close_p < vwap_last:
        return "SELL"
    return "NONE"
