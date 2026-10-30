"""Regression tests for FER3ON_FINAL_CHANGELOG.md [EXPOSURE-1] and [EXPOSURE-2].

[EXPOSURE-1]: core.portfolio_risk_authority's aggregate exposure cap
(MAX_RISK_TOTAL) sums the `risk_percent` field recorded per open trade. Before
this fix, callers recorded the *nominal* pre-sizing risk_percent (a small
0.10-0.75% figure from an unrelated formula in main.py), not the actual
dollar risk implied by the final lot and SL. After [SLTP-2]'s MIN_LOT_RISK_GUARD,
actual risk on a $200-$1000 account is typically ~1-5% per trade -- so the
exposure cap was checking aggregate risk against numbers 5-10x too small and
could never trigger before real risk got dangerous.

[EXPOSURE-2]: all active entries share the same-direction concentration cap.
"""
from unittest.mock import MagicMock, patch

import core.risk_manager as rm
import core.portfolio_risk_authority as pra


def test_compute_realized_risk_percent_matches_sltp2_calibration():
    """A 0.01 lot XAUUSD trade with a $10 stop should show ~5% risk on a
    $200 balance and ~1% on a $1000 balance -- matching the SLTP-2 table."""
    fake_sym_info = MagicMock()
    fake_sym_info.trade_tick_value = 1.0
    fake_sym_info.point = 0.01

    with patch.object(rm, "mt5", fake_mt5 := MagicMock()):
        fake_mt5.symbol_info.return_value = fake_sym_info
        with patch.object(rm, "MT5_AVAILABLE", True):
            pct_200 = rm.compute_realized_risk_percent(
                lot=0.01, entry_price=2650.00, sl_price=2640.00, balance=200.0,
            )
            pct_1000 = rm.compute_realized_risk_percent(
                lot=0.01, entry_price=2650.00, sl_price=2640.00, balance=1000.0,
            )

    assert 4.5 <= pct_200 <= 5.5
    assert 0.9 <= pct_1000 <= 1.1


def test_realized_exposure_blocks_second_trade_on_small_account():
    """After recording one trade at its REALIZED risk (~5% on $200),
    portfolio_risk_authority's exposure cap should block a second concurrent
    trade -- this could not happen before [EXPOSURE-1] because the exposure
    tracker only ever saw the tiny nominal risk_percent."""
    pra.__test_reset__()
    pra.reset_portfolio_state(balance=200.0)

    pra.record_trade_open(
        ticket=1, strategy="DAILY", direction="BUY", lot=0.01,
        risk_percent=5.0,  # realized risk, as [EXPOSURE-1] now records
        entry_price=2650.0, sl=2640.0, tp=2670.0,
    )

    decision = pra.evaluate_risk(
        strategy="SMC", direction="BUY", requested_risk_percent=0.5,
    )

    assert not decision.approved
    assert decision.rejection_reason == "EXPOSURE_LIMIT_HIT"

    pra.__test_reset__()
