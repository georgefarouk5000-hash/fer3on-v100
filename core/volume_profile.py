# =========================================
# FER3ON — VOLUME PROFILE (REAL)
# POC / VAH / VAL / HVN / LVN
# =========================================
# ملاحظة مهنية: بما أن MT5 غالبًا يعطينا Tick Volume (وليس Real Volume) على أدوات
# الفوركس والمعادن، الحساب هنا يعتمد على أفضل بديل متاح من الشمعة نفسها:
#   - إن كان "real_volume" موجودًا في الشمعة (بعض الوسطاء يوفّرونه) نستخدمه.
#   - وإلا نستخدم "tick_volume".
#   - وإلا نتراجع إلى وزن = 1 لكل شمعة (Time-Weighted Profile) بشكل شفّاف.
# الاسم الذي نُرجعه في الناتج (source) يوضّح ذلك بصراحة، دون تضليل.
#
# الخوارزمية:
#   1) نحدد نطاق السعر [min_low, max_high] خلال آخر lookback شمعة.
#   2) نقسّم النطاق إلى bins متساوية (افتراضي 24).
#   3) لكل شمعة: نوزّع حجمها بالتساوي على الـ bins التي تغطيها الشمعة
#      من low إلى high (uniform-inside-candle distribution). هذا تقريب معياري
#      يستخدمه معظم منصات التداول للـ Volume Profile عندما لا تتوفر بيانات
#      داخل-الشمعة (intra-bar).
#   4) POC = bin ذو أعلى حجم تراكمي.
#   5) Value Area (VA) = أضيق نطاق يحوي 70% من إجمالي الحجم حول POC.
#   6) HVN / LVN = العُقد ذات الحجم الأعلى / الأدنى بشكل نسبي.

from __future__ import annotations

from typing import Any, Dict, List


# -----------------------------
# مساعدات آمنة لقراءة الشمعة
# -----------------------------

def _cf(rate: Any, key: str, default: float = 0.0) -> float:
    """قراءة حقل رقمي من شمعة (dict أو numpy record) بأمان."""
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


def _candle_weight(rate: Any) -> tuple[float, str]:
    """
    يُعيد (وزن_الشمعة, نوع_الوزن).
    نوع_الوزن ∈ {"real_volume", "tick_volume", "uniform"}.
    """
    real_v = _cf(rate, "real_volume", 0.0)
    if real_v > 0:
        return real_v, "real_volume"
    tick_v = _cf(rate, "tick_volume", 0.0)
    if tick_v > 0:
        return tick_v, "tick_volume"
    # بعض المصادر تسمي الحقل volume فقط
    v = _cf(rate, "volume", 0.0)
    if v > 0:
        return v, "tick_volume"
    return 1.0, "uniform"


# -----------------------------
# الحساب الأساسي
# -----------------------------

def compute_volume_profile(
    rates: List[Any],
    bins: int = 24,
    lookback: int = 120,
    value_area_pct: float = 0.70,
) -> Dict[str, Any]:
    """
    يبني Volume Profile حقيقي من قائمة الشموع.

    المعطيات:
      rates          : قائمة شموع (dict أو mt5 rate)
      bins           : عدد شرائح السعر (افتراضي 24)
      lookback       : كم شمعة أخيرة نأخذ
      value_area_pct : نسبة الحجم داخل Value Area (شائع 70%)

    يُعيد dict فيه:
      poc, vah, val, high, low,
      bin_size, bins, hist (bin_low, bin_high, volume, is_poc, is_va),
      hvn, lvn, source (real_volume|tick_volume|uniform|mixed), valid
    """
    if not rates:
        return _empty_profile("no_rates")

    window = rates[-max(1, int(lookback)):]
    if len(window) < 5:
        return _empty_profile("insufficient_rates")

    highs = [_cf(r, "high", 0.0) for r in window]
    lows = [_cf(r, "low", 0.0) for r in window]
    highs = [h for h in highs if h > 0]
    lows = [l for l in lows if l > 0]
    if not highs or not lows:
        return _empty_profile("no_valid_prices")

    price_high = max(highs)
    price_low = min(lows)
    if price_high <= price_low:
        return _empty_profile("degenerate_range")

    bins = max(6, min(int(bins), 200))
    bin_size = (price_high - price_low) / bins
    hist = [0.0] * bins
    sources_seen: dict[str, int] = {}

    for rate in window:
        r_high = _cf(rate, "high", 0.0)
        r_low = _cf(rate, "low", 0.0)
        if r_high <= 0 or r_low <= 0 or r_high < r_low:
            continue
        weight, wtype = _candle_weight(rate)
        sources_seen[wtype] = sources_seen.get(wtype, 0) + 1

        lo_idx = int((r_low - price_low) / bin_size)
        hi_idx = int((r_high - price_low) / bin_size)
        lo_idx = max(0, min(lo_idx, bins - 1))
        hi_idx = max(0, min(hi_idx, bins - 1))
        span = hi_idx - lo_idx + 1
        if span <= 0:
            continue
        per_bin = weight / span
        for i in range(lo_idx, hi_idx + 1):
            hist[i] += per_bin

    total_volume = sum(hist)
    if total_volume <= 0:
        return _empty_profile("zero_total_volume")

    # POC
    poc_idx = max(range(bins), key=lambda i: hist[i])
    poc_price = price_low + (poc_idx + 0.5) * bin_size

    # Value Area — نمط شائع: من POC نتوسّع لأعلى/أسفل بأكبر مجاورين حتى نصل 70%.
    target = total_volume * float(value_area_pct)
    included = {poc_idx}
    running = hist[poc_idx]
    up = poc_idx + 1
    down = poc_idx - 1
    while running < target and (up < bins or down >= 0):
        up_vol = hist[up] if up < bins else -1.0
        dn_vol = hist[down] if down >= 0 else -1.0
        if up_vol < 0 and dn_vol < 0:
            break
        if up_vol >= dn_vol:
            if up < bins:
                included.add(up)
                running += hist[up]
                up += 1
            else:
                included.add(down)
                running += hist[down] if hist[down] > 0 else 0
                down -= 1
        else:
            if down >= 0:
                included.add(down)
                running += hist[down]
                down -= 1
            else:
                included.add(up)
                running += hist[up] if up < bins else 0
                up += 1

    va_indices = sorted(included)
    val_idx = va_indices[0]
    vah_idx = va_indices[-1]
    val_price = price_low + val_idx * bin_size
    vah_price = price_low + (vah_idx + 1) * bin_size

    # HVN / LVN — أعلى 3 و أدنى 3 (تتجاهل bins بحجم = 0)
    sorted_bins = sorted(range(bins), key=lambda i: hist[i], reverse=True)
    hvn_indices = [i for i in sorted_bins if hist[i] > 0][:3]
    lvn_indices = [i for i in sorted(range(bins), key=lambda i: hist[i]) if hist[i] > 0][:3]

    hist_out = []
    for i in range(bins):
        hist_out.append({
            "bin_low": price_low + i * bin_size,
            "bin_high": price_low + (i + 1) * bin_size,
            "volume": hist[i],
            "is_poc": i == poc_idx,
            "is_va": i in included,
        })

    # نوع المصدر: إن كل الأوزان جاءت من نوع واحد نعلن به، وإلا mixed.
    if len(sources_seen) == 1:
        source = next(iter(sources_seen))
    elif len(sources_seen) > 1:
        source = "mixed"
    else:
        source = "uniform"

    return {
        "valid": True,
        "poc": poc_price,
        "vah": vah_price,
        "val": val_price,
        "high": price_high,
        "low": price_low,
        "bin_size": bin_size,
        "bins": bins,
        "hist": hist_out,
        "hvn": [price_low + (i + 0.5) * bin_size for i in hvn_indices],
        "lvn": [price_low + (i + 0.5) * bin_size for i in lvn_indices],
        "total_volume": total_volume,
        "value_area_pct": value_area_pct,
        "source": source,
        "sources_breakdown": sources_seen,
        "lookback_used": len(window),
    }


def _empty_profile(reason: str) -> Dict[str, Any]:
    return {
        "valid": False,
        "reason": reason,
        "poc": 0.0,
        "vah": 0.0,
        "val": 0.0,
        "high": 0.0,
        "low": 0.0,
        "bin_size": 0.0,
        "bins": 0,
        "hist": [],
        "hvn": [],
        "lvn": [],
        "total_volume": 0.0,
        "value_area_pct": 0.0,
        "source": "none",
        "sources_breakdown": {},
        "lookback_used": 0,
    }


# -----------------------------
# استنتاجات جاهزة للاستخدام في القرار
# -----------------------------

def price_context_vs_profile(profile: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """
    يشرح موقع السعر الحالي بالنسبة لبروفايل الحجم.
    مفيد لـ FAIE / SMC agent.
    """
    if not profile or not profile.get("valid"):
        return {
            "position": "UNKNOWN",
            "distance_to_poc": 0.0,
            "in_value_area": False,
            "acceptance": "UNKNOWN",
        }

    poc = float(profile["poc"])
    vah = float(profile["vah"])
    val = float(profile["val"])
    price = float(current_price or 0.0)
    if price <= 0:
        return {
            "position": "UNKNOWN",
            "distance_to_poc": 0.0,
            "in_value_area": False,
            "acceptance": "UNKNOWN",
        }

    if price > vah:
        position = "ABOVE_VALUE_AREA"
    elif price < val:
        position = "BELOW_VALUE_AREA"
    else:
        position = "INSIDE_VALUE_AREA"

    # قبول (acceptance) بسيط: قرب السعر من POC يشير إلى منطقة قبول قوي.
    bin_size = float(profile.get("bin_size", 0.0)) or 1e-9
    dist_bins = abs(price - poc) / bin_size
    if dist_bins <= 1.0:
        acceptance = "STRONG_ACCEPTANCE"
    elif position == "INSIDE_VALUE_AREA":
        acceptance = "MODERATE_ACCEPTANCE"
    else:
        acceptance = "REJECTION_ZONE"

    return {
        "position": position,
        "distance_to_poc": abs(price - poc),
        "in_value_area": position == "INSIDE_VALUE_AREA",
        "acceptance": acceptance,
    }
