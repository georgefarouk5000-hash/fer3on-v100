"""Regression tests for FER3ON_FINAL_CHANGELOG.md [SLTP-1] and [SLTP-2].

[SLTP-1]: MIN_SL_DISTANCE is a "points" setting and must be converted with
`* point` before being compared against sl_dist (which is in RAW PRICE
UNITS, confirmed by core/trailing_stop.py's `current_price - trailing_distance`
against an absolute MT5 price). Before this fix, the floor was compared
unconverted and always won, silently discarding the adaptive SL/TP engine's
real output on every single trade.

[SLTP-2]: the stop distance is additionally capped at MAX_SL_DISTANCE_DOLLARS,
and core.risk_manager.calculate_smart_lot's lot-sizing formula converts the
(now correctly-scaled) stop distance to points before applying MT5's
tick-value convention.
"""
from unittest.mock import MagicMock, patch

import core.trade_executor as te
from core.settings import MIN_SL_DISTANCE, MAX_SL_DISTANCE_DOLLARS


def test_enforce_min_stop_distance_lets_adaptive_value_through():
    """A realistic adaptive SL (well above the tiny converted floor, well
    below the MAX_SL_DISTANCE_DOLLARS cap) must pass through unchanged --
    not get silently overridden to the raw (unconverted) MIN_SL_DISTANCE."""
    with patch.object(te, "MT5_AVAILABLE", False):
        # A stop distance comfortably between the floor and the cap.
        realistic_adaptive_sl = min(8.0, MAX_SL_DISTANCE_DOLLARS - 1.0)
        result = te._enforce_min_stop_distance("XAUUSD", realistic_adaptive_sl, point=0.01)

    assert result == realistic_adaptive_sl, (
        f"Expected the adaptive value {realistic_adaptive_sl} to pass through "
        f"unchanged, got {result} -- MIN_SL_DISTANCE floor bug may have "
        f"regressed (see [SLTP-1])."
    )
    # Sanity: the floor itself must be tiny (converted), not the raw setting.
    assert MIN_SL_DISTANCE * 0.01 < 6.0


def test_enforce_min_stop_distance_caps_oversized_adaptive_value():
    """An oversized adaptive SL (e.g. from an ATR spike) must be capped at
    MAX_SL_DISTANCE_DOLLARS, not sent to the broker as-is (see [SLTP-2])."""
    with patch.object(te, "MT5_AVAILABLE", False):
        oversized = MAX_SL_DISTANCE_DOLLARS + 50.0
        result = te._enforce_min_stop_distance("XAUUSD", oversized, point=0.01)

    assert result == MAX_SL_DISTANCE_DOLLARS


def test_enforce_min_stop_distance_floors_invalid_input():
    """sl_dist=None (ATR computation failed) must fall back to the (small,
    converted) floor -- never to the raw unconverted MIN_SL_DISTANCE."""
    with patch.object(te, "MT5_AVAILABLE", False):
        result = te._enforce_min_stop_distance("XAUUSD", None, point=0.01)

    assert result < 10.0, (
        f"Fallback floor was {result} -- looks like the raw (unconverted) "
        f"MIN_SL_DISTANCE={MIN_SL_DISTANCE} leaked through again."
    )


def test_calculate_smart_lot_uses_points_not_raw_price_for_tick_value():
    """The lot-sizing formula must convert the (raw price) stop distance to
    points before multiplying by tick_value, or lot sizes come out ~100x
    wrong for gold (see [SLTP-2])."""
    import core.risk_manager as rm

    fake_sym_info = MagicMock()
    fake_sym_info.trade_tick_value = 1.0
    fake_sym_info.volume_step = 0.01
    fake_sym_info.point = 0.01

    with patch.object(rm, "mt5") as fake_mt5:
        fake_mt5.symbol_info.return_value = fake_sym_info
        with patch.object(
            rm, "get_loss_limits_status",
            return_value={"daily_used": 0, "daily_limit": 999,
                          "weekly_used": 0, "weekly_limit": 999},
        ):
            with patch.object(rm, "cooldown_active", return_value=False):
                lot, raw_lot, _ = rm.calculate_smart_lot(
                    balance=1000.0,
                    risk_percent=1.0,
                    sl_dist=10.0,  # $10 raw price stop
                    symbol="XAUUSD",
                    quality_score=75,
                    session="LONDON",
                    exec_grade="A",
                )

    # risk_amount=$10, sl_points=1000, tick_value=1.0 -> raw_lot = 10/1000 = 0.01
    assert 0.005 <= raw_lot <= 0.02, (
        f"raw_lot={raw_lot} looks off by ~100x -- points/price-unit "
        f"conversion may have regressed (see [SLTP-2])."
    )
