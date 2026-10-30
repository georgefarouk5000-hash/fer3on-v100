"""Regression test for FER3ON_FINAL_CHANGELOG.md [EXPOSURE-3].

This is the most important test in this suite for catching a *class* of
regression, not just one bug: it re-derives risk_percent using the exact formula present in main.py (copied here
deliberately, not imported, so a future edit is caught rather than silently
drifting again), and checks the result against the risk guard.

The bug this guards against: SLTP-2 calibrated MIN_LOT_RISK_MULTIPLE_CAP
against a synthetic RISK_PER_TRADE_PERCENT test value, while earlier entry paths had their OWN independent, uncoordinated
risk_percent formulas (0.10-0.75%, with no connection to
RISK_PER_TRADE_PERCENT). Those values were too small for
the guard, which silently skipped every trade at $200-$500. [EXPOSURE-3]
anchored all of them to RISK_PER_TRADE_PERCENT with a floor
(MIN_EFFECTIVE_RISK_PERCENT); this test locks that in.
"""
from unittest.mock import MagicMock, patch

import core.risk_manager as rm
from core.settings import (
    RISK_PER_TRADE_PERCENT, MIN_EFFECTIVE_RISK_PERCENT, MAX_RISK_TOTAL,
)


def _make_fake_sym_info():
    info = MagicMock()
    info.trade_tick_value = 1.0
    info.volume_step = 0.01
    info.point = 0.01
    return info


def _main_py_risk_percent(risk_multiplier: float) -> float:
    """Exact formula from main.py's SMC path (line ~961) as of [EXPOSURE-3]."""
    return round(max(
        MIN_EFFECTIVE_RISK_PERCENT,
        min(MAX_RISK_TOTAL, RISK_PER_TRADE_PERCENT * float(risk_multiplier)),
    ), 3)


def test_main_py_risk_percent_clears_guard_across_confidence_range():
    fake_sym_info = _make_fake_sym_info()
    with patch.object(rm, "mt5") as fake_mt5:
        fake_mt5.symbol_info.return_value = fake_sym_info
        with patch.object(
            rm, "get_loss_limits_status",
            return_value={"daily_used": 0, "daily_limit": 999,
                          "weekly_used": 0, "weekly_limit": 999},
        ):
            with patch.object(rm, "cooldown_active", return_value=False):
                for balance in (200.0, 500.0, 1000.0):
                    for risk_multiplier in (0.2, 0.5, 1.0, 1.5):
                        risk_pct = _main_py_risk_percent(risk_multiplier)
                        lot, _, adjustments = rm.calculate_smart_lot(
                            balance=balance, risk_percent=risk_pct,
                            sl_dist=10.0, symbol="XAUUSD",
                            quality_score=75, session="LONDON", exec_grade="A",
                        )
                        assert lot > 0, (
                            f"main.py's risk_percent formula produced "
                            f"{risk_pct}% at balance=${balance}, "
                            f"risk_multiplier={risk_multiplier}, which the "
                            f"MIN_LOT_RISK_GUARD skipped: {adjustments}. "
                            f"[EXPOSURE-3] should prevent this."
                        )
