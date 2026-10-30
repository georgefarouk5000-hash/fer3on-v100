from __future__ import annotations

from typing import Any

from fer3on_masr.kernel.models import CandlePrediction

# =============================================================================
# CANDLE INTELLIGENCE — FULL CLASSIC PATTERN TAXONOMY
# =============================================================================
# النسخة القديمة كانت تحسب 3 "تنبؤات" فقط (Bullish Engulf / Doji / Bearish Pin)
# من معادلة عامة واحدة مطبّقة على آخر شمعة فقط — لا Hammer حقيقي، لا Marubozu،
# لا Star patterns (تحتاج 3 شموع)، ولا Engulfing حقيقي (يحتاج مقارنة فعلية
# بالشمعة السابقة، وليس معادلة على شمعة واحدة).
#
# هذه النسخة تُطبّق تعريفات هندسية حقيقية (نسب الجسم/الفتيل/المدى) لكل نمط
# كلاسيكي معروف، على شمعة واحدة أو اثنتين أو ثلاث حسب النمط، وتُرجع درجة
# تطابق مستمرة (0-100) بدل قرار ثنائي فقط — لتبقى قابلة للترتيب والمقارنة.
#
# قيد صريح يجب عدم تجاهله: هذا تصنيف هندسي (geometric classification) قائم
# على التعريفات الكلاسيكية المعروفة لأنماط الشموع، وليس نموذج تعلّم آلي مُدرَّب
# على بيانات تاريخية فعلية يُثبت جدوى تنبؤية لهذه الأنماط. جدوى أي نمط شمعة
# بمفرده (بدون سياق اتجاه/دعم/مقاومة/سيولة) محدودة تجريبيًا — راجع
# BACKTEST_VALIDITY_NOTICE.md. Hammer/Hanging Man وInverted Hammer/Shooting
# Star يتشاركان نفس الهندسة تمامًا؛ الفارق الوحيد بينهما هو اتجاه الترند
# السابق، لذا هذا الملف يفحص الترند القصير قبل الشمعة الحالية (rates التاريخية
# المُمرَّرة) للتفريق بينهما بدل تخمين عشوائي.


Candle = tuple[float, float, float, float]  # (open, high, low, close)


def _extract(rate: Any) -> Candle:
    if isinstance(rate, dict):
        return (
            float(rate.get("open", 0.0) or 0.0),
            float(rate.get("high", 0.0) or 0.0),
            float(rate.get("low", 0.0) or 0.0),
            float(rate.get("close", 0.0) or 0.0),
        )
    return (
        float(getattr(rate, "open", 0.0) or 0.0),
        float(getattr(rate, "high", 0.0) or 0.0),
        float(getattr(rate, "low", 0.0) or 0.0),
        float(getattr(rate, "close", 0.0) or 0.0),
    )


def _body(c: Candle) -> float:
    return abs(c[3] - c[0])


def _range(c: Candle) -> float:
    return max(c[1] - c[2], 1e-9)


def _upper_wick(c: Candle) -> float:
    return max(c[1] - max(c[0], c[3]), 0.0)


def _lower_wick(c: Candle) -> float:
    return max(min(c[0], c[3]) - c[2], 0.0)


def _is_bull(c: Candle) -> bool:
    return c[3] >= c[0]


def _body_ratio(c: Candle) -> float:
    return _body(c) / _range(c)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _preceding_trend(rates: list[Any], lookback: int = 6) -> str:
    """اتجاه قصير المدى قبل الشمعة الحالية (يستثنيها) — يُستخدم فقط للتفريق
    بين أزواج الأنماط متطابقة الهندسة (Hammer/Hanging Man، Inverted
    Hammer/Shooting Star)."""
    closes = []
    for rate in (rates or [])[-(lookback + 1):-1]:
        closes.append(_extract(rate)[3])
    if len(closes) < 2:
        return "FLAT"
    if closes[-1] > closes[0]:
        return "UP"
    if closes[-1] < closes[0]:
        return "DOWN"
    return "FLAT"


# =============================================================================
# SINGLE-CANDLE PATTERNS
# =============================================================================

def _doji_score(c: Candle) -> float:
    ratio = _body_ratio(c)
    return _clamp(100.0 * (1.0 - ratio / 0.12)) if ratio <= 0.12 else 0.0


def _dragonfly_doji(c: Candle) -> float:
    base = _doji_score(c)
    if base <= 0:
        return 0.0
    lw, uw = _lower_wick(c), _upper_wick(c)
    if lw <= 0:
        return 0.0
    dominance = _clamp(100.0 * (lw / max(lw + uw, 1e-9) - 0.5) * 2.0)
    return round((base * 0.5 + dominance * 0.5), 2)


def _gravestone_doji(c: Candle) -> float:
    base = _doji_score(c)
    if base <= 0:
        return 0.0
    lw, uw = _lower_wick(c), _upper_wick(c)
    if uw <= 0:
        return 0.0
    dominance = _clamp(100.0 * (uw / max(lw + uw, 1e-9) - 0.5) * 2.0)
    return round((base * 0.5 + dominance * 0.5), 2)


def _hammer_or_hanging_geometry(c: Candle) -> float:
    body, lw, uw = _body(c), _lower_wick(c), _upper_wick(c)
    if body <= 0:
        return 0.0
    lw_ratio = lw / body
    uw_ratio = uw / max(body, 1e-9)
    if lw_ratio < 1.8 or uw_ratio > 0.6:
        return 0.0
    score = _clamp(40.0 + (lw_ratio - 1.8) * 20.0 - uw_ratio * 30.0)
    return round(score, 2)


def _inverted_geometry(c: Candle) -> float:
    body, lw, uw = _body(c), _lower_wick(c), _upper_wick(c)
    if body <= 0:
        return 0.0
    uw_ratio = uw / body
    lw_ratio = lw / max(body, 1e-9)
    if uw_ratio < 1.8 or lw_ratio > 0.6:
        return 0.0
    score = _clamp(40.0 + (uw_ratio - 1.8) * 20.0 - lw_ratio * 30.0)
    return round(score, 2)


def _marubozu(c: Candle, bullish: bool) -> float:
    if _is_bull(c) != bullish:
        return 0.0
    ratio = _body_ratio(c)
    wick_frac = (_upper_wick(c) + _lower_wick(c)) / _range(c)
    if ratio < 0.85:
        return 0.0
    return round(_clamp(100.0 * ratio - wick_frac * 60.0), 2)


def _spinning_top(c: Candle) -> float:
    ratio = _body_ratio(c)
    if not (0.08 <= ratio <= 0.38):
        return 0.0
    lw, uw = _lower_wick(c), _upper_wick(c)
    if min(lw, uw) <= 0:
        return 0.0
    balance = 1.0 - abs(lw - uw) / max(lw + uw, 1e-9)
    return round(_clamp(60.0 * balance + 40.0 * (1.0 - abs(ratio - 0.2) / 0.2)), 2)


# =============================================================================
# TWO-CANDLE PATTERNS
# =============================================================================

def _bullish_engulfing(prev: Candle, cur: Candle) -> float:
    if _is_bull(prev) or not _is_bull(cur):
        return 0.0
    if not (cur[0] <= prev[3] and cur[3] >= prev[0]):
        return 0.0
    coverage = _body(cur) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + (coverage - 1.0) * 40.0), 2)


def _bearish_engulfing(prev: Candle, cur: Candle) -> float:
    if not _is_bull(prev) or _is_bull(cur):
        return 0.0
    if not (cur[0] >= prev[3] and cur[3] <= prev[0]):
        return 0.0
    coverage = _body(cur) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + (coverage - 1.0) * 40.0), 2)


def _bullish_harami(prev: Candle, cur: Candle) -> float:
    if not _is_bull(prev) or _is_bull(cur):
        return 0.0
    if not (cur[0] > min(prev[0], prev[3]) and cur[3] < max(prev[0], prev[3])):
        return 0.0
    containment = 1.0 - _body(cur) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + containment * 50.0), 2)


def _bearish_harami(prev: Candle, cur: Candle) -> float:
    if _is_bull(prev) or not _is_bull(cur):
        return 0.0
    if not (cur[0] > min(prev[0], prev[3]) and cur[3] < max(prev[0], prev[3])):
        return 0.0
    containment = 1.0 - _body(cur) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + containment * 50.0), 2)


def _piercing_line(prev: Candle, cur: Candle) -> float:
    if not _is_bull(prev):
        return 0.0
    if not _is_bull(cur):
        return 0.0
    if cur[0] >= prev[2]:
        return 0.0
    midpoint = (prev[0] + prev[3]) / 2.0
    if not (cur[3] > midpoint and cur[3] < prev[0]):
        return 0.0
    depth = (cur[3] - midpoint) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + depth * 40.0), 2)


def _dark_cloud_cover(prev: Candle, cur: Candle) -> float:
    if not _is_bull(prev):
        return 0.0
    if _is_bull(cur):
        return 0.0
    if cur[0] <= prev[1]:
        return 0.0
    midpoint = (prev[0] + prev[3]) / 2.0
    if not (cur[3] < midpoint and cur[3] > prev[0]):
        return 0.0
    depth = (midpoint - cur[3]) / max(_body(prev), 1e-9)
    return round(_clamp(50.0 + depth * 40.0), 2)


def _tweezer_top(prev: Candle, cur: Candle) -> float:
    tol = max(_range(prev), _range(cur)) * 0.08
    if abs(prev[1] - cur[1]) > tol:
        return 0.0
    if not (_is_bull(prev) and not _is_bull(cur)):
        return 0.0
    closeness = 1.0 - abs(prev[1] - cur[1]) / max(tol, 1e-9)
    return round(_clamp(45.0 + closeness * 55.0), 2)


def _tweezer_bottom(prev: Candle, cur: Candle) -> float:
    tol = max(_range(prev), _range(cur)) * 0.08
    if abs(prev[2] - cur[2]) > tol:
        return 0.0
    if not (not _is_bull(prev) and _is_bull(cur)):
        return 0.0
    closeness = 1.0 - abs(prev[2] - cur[2]) / max(tol, 1e-9)
    return round(_clamp(45.0 + closeness * 55.0), 2)


# =============================================================================
# THREE-CANDLE PATTERNS
# =============================================================================

def _morning_star(c1: Candle, c2: Candle, c3: Candle) -> float:
    if _is_bull(c1):
        return 0.0
    if not _is_bull(c3):
        return 0.0
    if _body_ratio(c1) < 0.5 or _body_ratio(c3) < 0.5:
        return 0.0
    if _body_ratio(c2) > 0.35:
        return 0.0
    midpoint1 = (c1[0] + c1[3]) / 2.0
    if c3[3] <= midpoint1:
        return 0.0
    penetration = (c3[3] - midpoint1) / max(_body(c1), 1e-9)
    gap_quality = 1.0 if max(c2[0], c2[3]) <= c1[3] + _range(c1) * 0.15 else 0.6
    return round(_clamp(45.0 + penetration * 35.0 * gap_quality), 2)


def _evening_star(c1: Candle, c2: Candle, c3: Candle) -> float:
    if not _is_bull(c1):
        return 0.0
    if _is_bull(c3):
        return 0.0
    if _body_ratio(c1) < 0.5 or _body_ratio(c3) < 0.5:
        return 0.0
    if _body_ratio(c2) > 0.35:
        return 0.0
    midpoint1 = (c1[0] + c1[3]) / 2.0
    if c3[3] >= midpoint1:
        return 0.0
    penetration = (midpoint1 - c3[3]) / max(_body(c1), 1e-9)
    gap_quality = 1.0 if min(c2[0], c2[3]) >= c1[3] - _range(c1) * 0.15 else 0.6
    return round(_clamp(45.0 + penetration * 35.0 * gap_quality), 2)


def _three_white_soldiers(c1: Candle, c2: Candle, c3: Candle) -> float:
    candles = (c1, c2, c3)
    if not all(_is_bull(c) for c in candles):
        return 0.0
    if not (c1[3] < c2[3] < c3[3]):
        return 0.0
    if not all(_body_ratio(c) >= 0.45 for c in candles):
        return 0.0
    opens_within = all(candles[i][0] >= candles[i - 1][0] for i in range(1, 3))
    quality = sum(_body_ratio(c) for c in candles) / 3.0
    score = 40.0 + quality * 60.0
    if not opens_within:
        score -= 15.0
    return round(_clamp(score), 2)


def _three_black_crows(c1: Candle, c2: Candle, c3: Candle) -> float:
    candles = (c1, c2, c3)
    if any(_is_bull(c) for c in candles):
        return 0.0
    if not (c1[3] > c2[3] > c3[3]):
        return 0.0
    if not all(_body_ratio(c) >= 0.45 for c in candles):
        return 0.0
    opens_within = all(candles[i][0] <= candles[i - 1][0] for i in range(1, 3))
    quality = sum(_body_ratio(c) for c in candles) / 3.0
    score = 40.0 + quality * 60.0
    if not opens_within:
        score -= 15.0
    return round(_clamp(score), 2)


def _three_inside_up(c1: Candle, c2: Candle, c3: Candle) -> float:
    harami = _bullish_harami(c1, c2)
    if harami <= 0:
        return 0.0
    if not (_is_bull(c3) and c3[3] > c1[0]):
        return 0.0
    return round(_clamp(harami * 0.6 + 40.0), 2)


def _three_inside_down(c1: Candle, c2: Candle, c3: Candle) -> float:
    harami = _bearish_harami(c1, c2)
    if harami <= 0:
        return 0.0
    if not (not _is_bull(c3) and c3[3] < c1[0]):
        return 0.0
    return round(_clamp(harami * 0.6 + 40.0), 2)


class CandleIntelligence:
    """يفحص كل أنماط الشموع الكلاسيكية المعروفة على آخر 1-3 شموع، ويُرجع
    درجة تطابق مستمرة لكل نمط (0-100)، مرتبة تنازليًا. كل الأنماط "مسجّلة"
    (registered) دومًا في الإخراج حتى لو كانت درجتها صفرًا — لتأكيد أنها
    مفعّلة وتعمل فعليًا، وليس فقط الأنماط التي صادف ظهورها."""

    @staticmethod
    def _candle(rate: Any) -> Candle:
        return _extract(rate)

    def predict(self, rates: list[Any]) -> list[CandlePrediction]:
        if not rates:
            rates = [{"open": 1.0, "high": 1.3, "low": 0.9, "close": 1.2}]

        c1 = self._candle(rates[-1])
        c2 = self._candle(rates[-2]) if len(rates) >= 2 else None
        c3 = self._candle(rates[-3]) if len(rates) >= 3 else None
        trend = _preceding_trend(rates)

        preds: list[CandlePrediction] = []

        def add(label: str, score: float, candles_required: int, extra: dict[str, Any] | None = None) -> None:
            details = {"candles_required": candles_required, "preceding_trend": trend}
            if extra:
                details.update(extra)
            preds.append(CandlePrediction(label, round(_clamp(score), 2), details))

        # --- single-candle ---
        add("Doji", _doji_score(c1), 1)
        add("Dragonfly Doji", _dragonfly_doji(c1), 1)
        add("Gravestone Doji", _gravestone_doji(c1), 1)
        add("Bullish Marubozu", _marubozu(c1, True), 1)
        add("Bearish Marubozu", _marubozu(c1, False), 1)
        add("Spinning Top", _spinning_top(c1), 1)

        hammer_geo = _hammer_or_hanging_geometry(c1)
        if trend == "DOWN":
            add("Hammer", hammer_geo, 1)
            add("Hanging Man", 0.0, 1, {"note": "preceding trend is DOWN, not UP -> geometry fits Hammer instead"})
        elif trend == "UP":
            add("Hanging Man", hammer_geo, 1)
            add("Hammer", 0.0, 1, {"note": "preceding trend is UP, not DOWN -> geometry fits Hanging Man instead"})
        else:
            add("Hammer", hammer_geo * 0.5, 1, {"note": "flat preceding trend -> ambiguous vs Hanging Man"})
            add("Hanging Man", hammer_geo * 0.5, 1, {"note": "flat preceding trend -> ambiguous vs Hammer"})

        inv_geo = _inverted_geometry(c1)
        if trend == "DOWN":
            add("Inverted Hammer", inv_geo, 1)
            add("Shooting Star", 0.0, 1, {"note": "preceding trend is DOWN, not UP -> geometry fits Inverted Hammer instead"})
        elif trend == "UP":
            add("Shooting Star", inv_geo, 1)
            add("Inverted Hammer", 0.0, 1, {"note": "preceding trend is UP, not DOWN -> geometry fits Shooting Star instead"})
        else:
            add("Inverted Hammer", inv_geo * 0.5, 1, {"note": "flat preceding trend -> ambiguous vs Shooting Star"})
            add("Shooting Star", inv_geo * 0.5, 1, {"note": "flat preceding trend -> ambiguous vs Inverted Hammer"})

        # --- two-candle ---
        if c2 is not None:
            add("Bullish Engulfing", _bullish_engulfing(c2, c1), 2)
            add("Bearish Engulfing", _bearish_engulfing(c2, c1), 2)
            add("Bullish Harami", _bullish_harami(c2, c1), 2)
            add("Bearish Harami", _bearish_harami(c2, c1), 2)
            add("Piercing Line", _piercing_line(c2, c1), 2)
            add("Dark Cloud Cover", _dark_cloud_cover(c2, c1), 2)
            add("Tweezer Top", _tweezer_top(c2, c1), 2)
            add("Tweezer Bottom", _tweezer_bottom(c2, c1), 2)
        else:
            for label in (
                "Bullish Engulfing", "Bearish Engulfing", "Bullish Harami", "Bearish Harami",
                "Piercing Line", "Dark Cloud Cover", "Tweezer Top", "Tweezer Bottom",
            ):
                add(label, 0.0, 2, {"note": "insufficient candles (need 2)"})

        # --- three-candle ---
        if c3 is not None:
            add("Morning Star", _morning_star(c3, c2, c1), 3)
            add("Evening Star", _evening_star(c3, c2, c1), 3)
            add("Three White Soldiers", _three_white_soldiers(c3, c2, c1), 3)
            add("Three Black Crows", _three_black_crows(c3, c2, c1), 3)
            add("Three Inside Up", _three_inside_up(c3, c2, c1), 3)
            add("Three Inside Down", _three_inside_down(c3, c2, c1), 3)
        else:
            for label in (
                "Morning Star", "Evening Star", "Three White Soldiers",
                "Three Black Crows", "Three Inside Up", "Three Inside Down",
            ):
                add(label, 0.0, 3, {"note": "insufficient candles (need 3)"})

        preds.sort(key=lambda item: item.probability, reverse=True)
        return preds
