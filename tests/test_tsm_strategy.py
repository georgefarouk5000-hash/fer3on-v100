from core.closed_rate_snapshot import closed_rates_asof
from core.tsm_strategy import (
    _major_swings,
    _m5_timing_confirms,
    _stop_anchor,
    _target,
)


def test_context_rates_exclude_candles_not_closed_at_decision_time():
    rates = [
        {"time": 0, "close": 1},
        {"time": 300, "close": 2},
        {"time": 600, "close": 3},
    ]

    assert closed_rates_asof(
        rates,
        timeframe_seconds=300,
        decision_time=600,
    ) == rates[:2]


def _rates(closes):
    return [
        {
            "time": index * 900,
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
        }
        for index, close in enumerate(closes)
    ]


def _swing_rates():
    return _rates([
        110, 108, 105, 102, 100, 103, 107, 112, 118, 125, 130, 126,
        120, 115, 112, 110, 113, 117, 121, 124, 125, 121, 116, 112,
        110, 108, 111, 114, 118, 121, 120, 116, 111, 107, 105, 103,
        106, 110, 113, 115, 112, 108, 104, 100, 96, 92, 90, 94, 98,
        100, 101, 102, 94, 98, 101, 100, 98, 99, 97, 96, 97, 95,
    ])


def test_stop_uses_last_prominent_lower_high_without_an_atr_stop_cap():
    rates = _swing_rates()

    selection = _stop_anchor(rates, "SELL", entry=100, atr_value=10)

    assert selection is not None
    anchor, reason = selection
    assert anchor.price == 115.2
    assert reason == "LAST_MAJOR_PROTECTED_LH"
    assert anchor.prominence_atr >= 1.0
    assert anchor.price > 101.2
    assert anchor.price + 10 * 0.15 > 100


def test_major_swings_ignore_small_pivots_that_lack_prominence():
    rates = _swing_rates()

    major = _major_swings(rates, atr_value=10)

    assert any(point.kind == "HIGH" and point.price == 125.2 for point in major)
    assert not any(point.kind == "HIGH" and point.price == 101.2 for point in major)


def test_stop_stays_beyond_the_latest_major_high_even_if_it_is_not_a_lower_high():
    rates = _rates([
        110, 108, 105, 102, 100, 103, 107, 112, 118, 125, 130, 126,
        120, 115, 112, 110, 113, 117, 121, 124, 125, 121, 116, 112,
        110, 108, 111, 114, 118, 121, 120, 116, 111, 107, 105, 103,
        106, 110, 113, 115, 112, 108, 104, 100, 96, 92, 90, 100, 110,
        120, 130, 140, 135, 125, 115, 105, 95, 90, 88, 86,
    ])

    selection = _stop_anchor(rates, "SELL", entry=100, atr_value=10)

    assert selection is not None
    anchor, reason = selection
    assert anchor.price == 140.2
    assert reason == "LAST_MAJOR_M15_HIGH"


def test_target_uses_next_structural_support_when_nearest_is_too_close():
    target = _target(
        _swing_rates(),
        entry=120,
        stop=130,
        signal="SELL",
        atr_value=10,
    )

    assert target is not None
    target_price, source, target_level, next_target = target
    assert source == "M15_SWING"
    assert target_level == 102.8
    assert target_price > target_level
    assert next_target is not None
    assert next_target < target_price
    assert 120 - target_price >= 12


def test_target_can_use_h1_structure_when_m15_has_no_major_opposing_swing():
    target = _target(
        [],
        entry=110,
        stop=120,
        signal="SELL",
        atr_value=2,
        h1_rates=_swing_rates(),
    )

    assert target is not None
    target_price, source, target_level, _ = target
    assert source == "H1_SWING"
    assert target_price > target_level


def test_m5_timing_confirmation_requires_a_closed_bar_in_signal_direction():
    rates = [
        {"open": 100, "close": 101, "high": 102, "low": 99},
        {"open": 101, "close": 102, "high": 103, "low": 100},
        {"open": 102, "close": 103, "high": 104, "low": 101},
        {"open": 104, "close": 105, "high": 106, "low": 103},
    ]

    assert _m5_timing_confirms(rates, "BUY")
    assert not _m5_timing_confirms(rates, "SELL")

    sell_rates = [
        {"open": 105, "close": 104, "high": 106, "low": 103},
        {"open": 104, "close": 103, "high": 105, "low": 102},
        {"open": 103, "close": 102, "high": 104, "low": 101},
        {"open": 101, "close": 100, "high": 102, "low": 99},
    ]
    assert _m5_timing_confirms(sell_rates, "SELL")
