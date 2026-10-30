# =============================================================================
# FER3ON V3.5 — Truth Layer Test (Phase-1 Acceptance)
# =============================================================================

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analytics.truth_layer import (
    TradeRecord,
    acceptance_smoke_test,
    __test_reset__,
    load_all_trades,
    compute_metrics,
    breakdown_by_strategy,
    breakdown_by_session,
    breakdown_by_regime,
)


class TruthLayerTests(unittest.TestCase):

    def setUp(self):
        __test_reset__()

    def test_01_smoke_test_returns_expected_shape(self):
        out = acceptance_smoke_test()
        self.assertEqual(out["trade_count"], 3)
        self.assertGreater(out["win_rate"], 0.5)
        self.assertTrue(out["by_strategy_breakdown_present"])
        self.assertTrue(out["by_session_breakdown_present"])
        self.assertTrue(out["by_regime_breakdown_present"])

    def test_02_metrics_consistency(self):
        acceptance_smoke_test()
        trades = load_all_trades()
        m = compute_metrics(trades)
        self.assertEqual(m.total_trades, 3)
        self.assertGreaterEqual(m.wins, 1)
        self.assertGreaterEqual(m.losses, 1)
        self.assertGreater(m.net_pnl, 0)

    def test_03_breakdown_keys(self):
        acceptance_smoke_test()
        trades = load_all_trades()
        by_strat = breakdown_by_strategy(trades)
        by_sess = breakdown_by_session(trades)
        by_reg = breakdown_by_regime(trades)
        self.assertIn("SMC", by_strat)
        self.assertIn("DAILY", by_strat)
        self.assertIn("LONDON", by_sess)
        self.assertIn("NEW_YORK", by_sess)
        self.assertIn("TRENDING", by_reg)
        self.assertIn("RANGING", by_reg)


def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(TruthLayerTests)
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
