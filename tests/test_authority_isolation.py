# =============================================================================
# FER3ON V3.5 — Authority Isolation Test (Phase-1 Acceptance)
# =============================================================================
# Validates that the Portfolio Risk Authority:
#   1. CAN reject for: emergency_stop, daily_loss, max_drawdown, exposure, lot_cap
#   2. CANNOT reject for: cross-strategy direction mismatch (diversification)
#   3. Does not decide BUY/SELL — risk-only
# =============================================================================

import unittest
import sys, os
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.portfolio_risk_authority import (
    PORTFOLIO_RISK_AUTHORITY_CAN_REJECT,
    PORTFOLIO_RISK_AUTHORITY_CANNOT_REJECT_FOR,
    is_acceptable_rejection_reason,
    get_portfolio_state,
    evaluate_risk,
    record_trade_open,
    record_trade_close,
    record_trade_partial_close,
    __test_reset__,
)


class AuthorityIsolationTests(unittest.TestCase):

    def setUp(self):
        __test_reset__()
        self.daily_pnl_patch = patch(
            "core.portfolio_risk_authority.get_daily_loss_status",
            return_value={"daily_pnl": 0.0, "daily_loss": 0.0},
        )
        self.daily_pnl_patch.start()
        self.addCleanup(self.daily_pnl_patch.stop)

    def test_01_can_reject_emergency_stop(self):
        self.assertIn("EMERGENCY_STOP", PORTFOLIO_RISK_AUTHORITY_CAN_REJECT)
        self.assertTrue(is_acceptable_rejection_reason("DAILY_LOSS_LIMIT_HIT"))

    def test_02_cannot_reject_cross_strategy_conflict(self):
        # DAILY=BUY, SMC=SELL scenario — Authority must NOT reject.
        # This is "Portfolio Diversification", not Conflict.
        self.assertFalse(is_acceptable_rejection_reason("STRATEGY_CONFLICT"))
        self.assertFalse(is_acceptable_rejection_reason("CROSS_STRATEGY_DIRECTION_MISMATCH"))
        self.assertFalse(is_acceptable_rejection_reason("BIAS_VS_STRATEGY_MISMATCH"))
        self.assertIn("STRATEGY_CONFLICT", PORTFOLIO_RISK_AUTHORITY_CANNOT_REJECT_FOR)

    def test_03_does_not_decide_direction(self):
        # Authority just accepts any direction at face value (decision is upstream).
        d = evaluate_risk(
            strategy="SMC",
            direction="BUY",
            requested_risk_percent=0.5,
        )
        self.assertTrue(d.approved)
        self.assertGreater(d.final_lot_estimate, 0)

    def test_04_rejects_when_daily_loss_exceeded(self):
        state = get_portfolio_state()
        # The hard daily loss ceiling is fixed, even on a larger account.
        state.day_start_balance = 5000.0
        state.current_equity = 1000.0
        with patch(
            "core.portfolio_risk_authority.get_daily_loss_status",
            return_value={"daily_pnl": -101.0, "daily_loss": 101.0},
        ):
            d = evaluate_risk(
                strategy="SMC",
                direction="BUY",
                requested_risk_percent=0.5,
            )
        self.assertFalse(d.approved)
        self.assertEqual(d.rejection_reason, "DAILY_LOSS_LIMIT_HIT")

    def test_09_fails_closed_when_mt5_daily_pnl_is_unavailable(self):
        with patch(
            "core.portfolio_risk_authority.get_daily_loss_status",
            side_effect=RuntimeError("MT5_DEAL_HISTORY_UNAVAILABLE"),
        ):
            decision = evaluate_risk(
                strategy="SMC",
                direction="BUY",
                requested_risk_percent=0.5,
            )
        self.assertFalse(decision.approved)
        self.assertEqual(decision.rejection_reason, "DAILY_PNL_UNAVAILABLE")

    def test_05_rejects_when_max_open(self):
        for i in range(5):
            record_trade_open(
                ticket=100 + i,
                strategy="SMC",
                direction="BUY",
                lot=0.01,
                risk_percent=0.2,
                entry_price=2000.0,
                sl=1999.0,
                tp=2001.0,
            )
        d = evaluate_risk(
            strategy="SMC",
            direction="BUY",
            requested_risk_percent=0.5,
        )
        self.assertFalse(d.approved)
        self.assertIn("OPEN", (d.rejection_reason or "").upper())

    def test_06_caps_exposure(self):
        state = get_portfolio_state()
        state.day_start_balance = 1000.0
        state.current_equity = 1000.0
        # Simulate an already-open trade with high exposure
        record_trade_open(
            ticket=999,
            strategy="DAILY",
            direction="BUY",
            lot=0.1,
            risk_percent=1.4,   # near MAX_RISK_TOTAL=1.5
            entry_price=2000.0,
            sl=1999.0,
            tp=2001.0,
        )
        d = evaluate_risk(
            strategy="SMC",
            direction="BUY",
            requested_risk_percent=0.5,
        )
        # Should trim (not reject) since headroom still exists.
        self.assertTrue(d.approved)
        # Headroom = 1.5 - 1.4 = 0.1
        self.assertLessEqual(d.final_risk_percent, 1.5)

    def test_07_partial_close_reduces_remaining_exposure(self):
        record_trade_open(
            ticket=777,
            strategy="SMC",
            direction="BUY",
            lot=0.10,
            risk_percent=1.0,
            entry_price=2000.0,
            sl=1990.0,
            tp=2020.0,
        )
        record_trade_partial_close(ticket=777, volume_closed=0.04, profit=8.0)

        state = get_portfolio_state()
        remaining = next(t for t in state.open_trades if t["ticket"] == 777)
        self.assertAlmostEqual(remaining["lot"], 0.06)
        self.assertAlmostEqual(remaining["risk_percent"], 0.6)
        self.assertEqual(len(state.open_trades), 1)
        self.assertAlmostEqual(state.daily_pnl, 8.0)

    def test_08_blocks_same_symbol_direction_across_strategies(self):
        for ticket, strategy in ((801, "DAILY"), (802, "DAILY")):
            record_trade_open(
                ticket=ticket,
                strategy=strategy,
                direction="BUY",
                lot=0.01,
                risk_percent=0.2,
                entry_price=2000.0,
                sl=1999.0,
                tp=2001.0,
                symbol="XAUUSD",
            )

        decision = evaluate_risk(
            strategy="SMC",
            direction="BUY",
            requested_risk_percent=0.5,
            candidate_meta={"symbol": "XAUUSD"},
        )
        self.assertFalse(decision.approved)
        self.assertEqual(decision.rejection_reason, "SYMBOL_DIRECTION_MAX_OPEN_HIT")


def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(AuthorityIsolationTests)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": res.testsRun,
        "failures": len(res.failures),
        "errors": len(res.errors),
        "ok": res.wasSuccessful(),
    }


if __name__ == "__main__":
    summary = run_all()
    import json
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["ok"] else 1)
