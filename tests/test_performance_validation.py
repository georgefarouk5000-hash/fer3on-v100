# =============================================================================
# FER3ON V3.5 — Performance Validation Test (Phase-1 Acceptance)
# =============================================================================
# Validates that analytics/setup_analyzer.py correctly answers:
#   "Which setup actually wins?"
# =============================================================================

import sys
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from analytics.truth_layer import TradeRecord, __test_reset__
from analytics.setup_analyzer import (
    analyze_setup,
    analyze_all_setups,
    acceptance_smoke_test,
    overall_setups_report,
    persist_setup_analysis_report,
)


class PerformanceValidationTests(unittest.TestCase):

    def setUp(self):
        __test_reset__()

    def test_01_analyze_all_strategies_returns_metrics(self):
        out = acceptance_smoke_test()
        # Active strategies present in the analyzer
        self.assertEqual(out["expected_strategies_present"],
                         sorted(["SMC", "DAILY"]))

    def test_02_ranking_invariant(self):
        out = acceptance_smoke_test()
        # ranks are 1..N
        items = out["analyze_setup_seed_smoke"]
        ranks = [i["rank"] for i in items]
        self.assertEqual(sorted(ranks), list(range(1, len(items) + 1)))

    def test_03_overall_report_shape(self):
        rep = overall_setups_report()
        self.assertIn("strategies", rep)
        self.assertIn("ranking", rep)
        for s in ("SMC", "DAILY"):
            self.assertIn(s, rep["strategies"])

    def test_04_verdict_key_words(self):
        with patch(
            "analytics.setup_analyzer.load_all_trades",
            side_effect=AssertionError("explicit empty trades must not load persisted data"),
        ):
            out = analyze_setup("SMC", trades=[])
        self.assertIn(out.verdict, ("INSUFFICIENT_SAMPLES", "PROFITABLE",
                                    "EDGE_PRESENT", "WEAK_NEGATIVE_EDGE", "MIXED"))
        self.assertEqual(out.metrics.total_trades, 0)

    def test_entry_reason_and_condition_breakdowns(self):
        base = dict(
            strategy="SMC",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            entry_reason="SMC: BOS + FVG",
            entry_conditions=["BOS", "FVG"],
        )
        trades = [
            TradeRecord(ticket=1, profit=10, is_win=True, **base),
            TradeRecord(ticket=2, profit=-5, is_win=False, **base),
        ]

        analysis = analyze_setup("SMC", trades=trades)
        report = analysis.to_dict()

        self.assertEqual(
            analysis.entry_reason_breakdown["SMC: BOS + FVG"].total_trades, 2
        )
        self.assertEqual(
            analysis.entry_condition_breakdown["BOS"].net_pnl, 5
        )
        self.assertEqual(
            report["entry_condition_breakdown"]["FVG"]["metrics"]["total_trades"],
            2,
        )
        self.assertFalse(
            report["entry_condition_breakdown"]["FVG"]["samples_sufficient"]
        )

    def test_setup_report_persists_to_requested_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = os.path.join(temp_dir, "setup_analysis.json")
            report = persist_setup_analysis_report(report_path=report_path)
            with open(report_path, encoding="utf-8") as handle:
                saved = __import__("json").load(handle)

            self.assertEqual(saved["strategies"], report["strategies"])
            self.assertIn("entry_condition_breakdown", saved["strategies"]["SMC"])


def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(PerformanceValidationTests)
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
