# =============================================================================
# FER3ON V3.5 — Risk Consistency Test (Phase-1 Acceptance)
# =============================================================================
# Validates the Risk Unification rule:
#   - core/settings.py is the SOLE source of risk values.
#   - Values in README/config are ignored at runtime.
#   - Authority reads from settings.phase only.
# =============================================================================

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.settings


class RiskConsistencyTests(unittest.TestCase):

    def test_01_settings_is_source_of_truth(self):
        # V3.5 unified values; settings.py overrides legacy config.
        self.assertEqual(core.settings.MAX_DAILY_LOSS_USD, 100.0)
        self.assertGreaterEqual(core.settings.RISK_PER_TRADE_PERCENT, 0.25)
        self.assertLessEqual(core.settings.RISK_PER_TRADE_PERCENT, 1.0)
        self.assertLessEqual(core.settings.MIN_EFFECTIVE_RISK_PERCENT, 1.0)
        self.assertAlmostEqual(
            core.settings.MAX_RISK_PER_DAY_PERCENT,
            core.settings.MAX_DAILY_LOSS_USD
            / core.settings.BASE_ACCOUNT_BALANCE * 100.0,
        )
        self.assertEqual(core.settings.MAX_DAILY_RISK, 100.0)

    def test_02_open_position_limits(self):
        self.assertEqual(core.settings.MAX_OPEN_TRADES, 4)
        self.assertEqual(core.settings.MAX_OPEN_PER_STRATEGY, 1)
        self.assertEqual(core.settings.MAX_OPEN_SMC, 1)
        self.assertEqual(core.settings.MAX_OPEN_DAILY, 1)
        self.assertEqual(
            set(core.settings.PER_STRATEGY_MAX_OPEN_LIMITS),
            {"SMC", "DAILY", "TSM"},
        )
        self.assertEqual(core.settings.MAX_OPEN_TSM, 1)

    def test_03_portfolio_authority_keys(self):
        self.assertTrue(core.settings.PORTFOLIO_RISK_AUTHORITY_ACTIVE)
        self.assertIn("EMERGENCY_STOP", core.settings.PORTFOLIO_RISK_AUTHORITY_CAN_REJECT)
        self.assertNotIn("STRATEGY_CONFLICT",
                         core.settings.PORTFOLIO_RISK_AUTHORITY_CAN_REJECT)

    def test_04_ml_authority_downgrade(self):
        self.assertEqual(core.settings.ML_AUTHORITY_WEIGHT, 0.0)
        self.assertLessEqual(core.settings.ML_BOOST_MAX_POINTS, 5)
        self.assertGreaterEqual(core.settings.ML_PENALTY_MAX_PTS, -5)
        self.assertFalse(core.settings.ML_BLOCK_ALLOWED)
        self.assertFalse(core.settings.ML_REJECT_ALLOWED)
        self.assertFalse(core.settings.ML_OVERRIDE_ALLOWED)

    def test_05_candle_confirmation_keys(self):
        self.assertTrue(core.settings.CANDLE_CONFIRMATION_ENABLED)
        self.assertTrue(core.settings.CANDLE_CONFIRMATION_REQUIRE_2_BARS)

    def test_06_truth_layer_paths_exist(self):
        self.assertTrue(core.settings.TRUTH_LAYER_TRADE_HISTORY.endswith(".json"))
        self.assertTrue(core.settings.TRUTH_LAYER_DAILY_REPORT.endswith(".json"))


def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(RiskConsistencyTests)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    return {
        "tests_run": res.testsRun,
        "failures": len(res.failures),
        "errors": len(res.errors),
        "ok": res.wasSuccessful(),
    }


if __name__ == "__main__":
    import json
    summary = run_all()
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["ok"] else 1)
