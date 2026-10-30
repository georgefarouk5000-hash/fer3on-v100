"""اختبارات CandleIntelligence: تتحقق أن كل نمط شمعة كلاسيكي (Doji, Hammer,
Engulfing, Star, Marubozu...) يُكتشف فعليًا على تركيب OHLC مطابق لتعريفه،
وأن الأزواج متطابقة الهندسة (Hammer/Hanging Man، Inverted Hammer/Shooting
Star) تُميَّز بشكل صحيح حسب الترند السابق."""

from __future__ import annotations

from fer3on_masr.intelligence.candles import CandleIntelligence

ci = CandleIntelligence()


def _top_label(rates, n=1):
    preds = ci.predict(rates)
    return preds[0].label if n == 1 else [p.label for p in preds[:n]]


def _score_of(rates, label):
    preds = ci.predict(rates)
    return next(p.probability for p in preds if p.label == label)


def _filler(n, base=100.0, step=0.0):
    out = []
    price = base
    for _ in range(n):
        o = price
        c = price + step
        h = max(o, c) + 0.1
        l = min(o, c) - 0.1
        out.append({"open": o, "high": h, "low": l, "close": c})
        price = c
    return out


def test_all_patterns_are_registered_every_cycle():
    # حتى مع بيانات محايدة، يجب أن تظهر كل الأنماط في الإخراج (بدرجة قد تكون
    # صفرًا) — إثبات أنها "مسجّلة" وتعمل فعليًا، وليست غائبة عن النظام.
    rates = _filler(10, 100, 0.1)
    labels = {p.label for p in ci.predict(rates)}
    expected = {
        "Doji", "Dragonfly Doji", "Gravestone Doji", "Bullish Marubozu",
        "Bearish Marubozu", "Spinning Top", "Hammer", "Hanging Man",
        "Inverted Hammer", "Shooting Star", "Bullish Engulfing",
        "Bearish Engulfing", "Bullish Harami", "Bearish Harami",
        "Piercing Line", "Dark Cloud Cover", "Tweezer Top", "Tweezer Bottom",
        "Morning Star", "Evening Star", "Three White Soldiers",
        "Three Black Crows", "Three Inside Up", "Three Inside Down",
    }
    assert expected.issubset(labels)


def test_doji():
    rates = _filler(6, 100, 0.3) + [{"open": 105.0, "high": 105.4, "low": 104.6, "close": 105.02}]
    assert _top_label(rates) == "Doji"


def test_hammer_after_downtrend():
    down = _filler(6, 110, -1.0)
    lc = down[-1]["close"]
    hammer = {"open": lc, "high": lc + 0.15, "low": lc - 2.0, "close": lc + 0.1}
    rates = down + [hammer]
    assert _top_label(rates) == "Hammer"
    assert _score_of(rates, "Hanging Man") == 0.0


def test_hanging_man_after_uptrend_same_geometry():
    up = _filler(6, 100, 1.0)
    lc = up[-1]["close"]
    shape = {"open": lc, "high": lc + 0.15, "low": lc - 2.0, "close": lc + 0.1}
    rates = up + [shape]
    assert _top_label(rates) == "Hanging Man"
    assert _score_of(rates, "Hammer") == 0.0


def test_shooting_star_after_uptrend():
    up = _filler(6, 100, 1.0)
    lc = up[-1]["close"]
    shape = {"open": lc, "high": lc + 2.0, "low": lc - 0.15, "close": lc - 0.1}
    rates = up + [shape]
    assert _top_label(rates) == "Shooting Star"
    assert _score_of(rates, "Inverted Hammer") == 0.0


def test_inverted_hammer_after_downtrend():
    down = _filler(6, 110, -1.0)
    lc = down[-1]["close"]
    shape = {"open": lc, "high": lc + 2.0, "low": lc - 0.15, "close": lc - 0.1}
    rates = down + [shape]
    assert _top_label(rates) == "Inverted Hammer"
    assert _score_of(rates, "Shooting Star") == 0.0


def test_bullish_marubozu():
    maru = {"open": 100.0, "high": 105.0, "low": 100.0, "close": 105.0}
    rates = _filler(3, 100, 0) + [maru]
    assert _top_label(rates) == "Bullish Marubozu"


def test_bearish_marubozu():
    maru = {"open": 105.0, "high": 105.0, "low": 100.0, "close": 100.0}
    rates = _filler(3, 100, 0) + [maru]
    assert _top_label(rates) == "Bearish Marubozu"


def test_bullish_engulfing():
    prev = {"open": 105.0, "high": 105.2, "low": 99.5, "close": 100.0}
    cur = {"open": 99.5, "high": 106.5, "low": 99.0, "close": 106.0}
    rates = _filler(3, 100, 0) + [prev, cur]
    assert _score_of(rates, "Bullish Engulfing") > 50.0


def test_bearish_engulfing():
    prev = {"open": 100.0, "high": 105.5, "low": 99.8, "close": 105.0}
    cur = {"open": 105.5, "high": 106.0, "low": 98.5, "close": 99.0}
    rates = _filler(3, 100, 0) + [prev, cur]
    assert _score_of(rates, "Bearish Engulfing") > 50.0


def test_morning_star():
    c1 = {"open": 110.0, "high": 110.2, "low": 100.0, "close": 101.0}
    c2 = {"open": 100.5, "high": 101.2, "low": 99.8, "close": 100.8}
    c3 = {"open": 101.2, "high": 108.0, "low": 101.0, "close": 107.0}
    rates = _filler(3, 110, 0) + [c1, c2, c3]
    assert _top_label(rates) == "Morning Star"


def test_evening_star():
    c1 = {"open": 100.0, "high": 110.2, "low": 99.8, "close": 109.5}
    c2 = {"open": 109.8, "high": 110.5, "low": 109.0, "close": 109.9}
    c3 = {"open": 109.0, "high": 109.2, "low": 102.0, "close": 103.0}
    rates = _filler(3, 100, 0) + [c1, c2, c3]
    assert _top_label(rates) == "Evening Star"


def test_three_white_soldiers():
    c1 = {"open": 100.0, "high": 103.3, "low": 99.8, "close": 103.0}
    c2 = {"open": 102.0, "high": 106.3, "low": 101.8, "close": 106.0}
    c3 = {"open": 105.0, "high": 109.3, "low": 104.8, "close": 109.0}
    rates = _filler(3, 100, 0) + [c1, c2, c3]
    assert _top_label(rates) == "Three White Soldiers"


def test_three_black_crows():
    c1 = {"open": 109.0, "high": 109.3, "low": 105.8, "close": 106.0}
    c2 = {"open": 107.0, "high": 107.3, "low": 102.8, "close": 103.0}
    c3 = {"open": 104.0, "high": 104.3, "low": 99.8, "close": 100.0}
    rates = _filler(3, 109, 0) + [c1, c2, c3]
    assert _top_label(rates) == "Three Black Crows"


def test_tweezer_bottom():
    c1 = {"open": 103.0, "high": 103.5, "low": 99.0, "close": 100.0}
    c2 = {"open": 100.5, "high": 104.0, "low": 99.05, "close": 103.5}
    rates = _filler(3, 103, 0) + [c1, c2]
    assert _top_label(rates) == "Tweezer Bottom"


def test_insufficient_candles_are_flagged_not_fabricated():
    preds = ci.predict([{"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5}])
    morning_star = next(p for p in preds if p.label == "Morning Star")
    assert morning_star.probability == 0.0
    assert morning_star.details.get("note") == "insufficient candles (need 3)"
