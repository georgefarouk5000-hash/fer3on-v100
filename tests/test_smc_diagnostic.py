# =============================================================================
# FER3ON V3.5 — SMC Diagnostic Test (Phase-1 Acceptance)
# =============================================================================
# Validates that smc_debug_report can record per-day detection rates for
# every primitive. Used to localize which SMC part is failing in production.
# =============================================================================

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.smc_debug_report import (
    acceptance_smoke_test,
    record_evaluation,
    get_today_summary,
    flush_report,
    __test_reset__,
    SMC_DEBUG_REPORT_DIR,
)


class SMCDiagnosticTests(unittest.TestCase):

    def setUp(self):
        __test_reset__()

    def test_01_smoke_test(self):
        out = acceptance_smoke_test()
        self.assertEqual(out["sweep_detections"], 20)        # 100/5
        self.assertAlmostEqual(out["sweep_rate"], 0.2, places=2)
        self.assertEqual(out["bos_detections"], 5)           # 100/20
        self.assertAlmostEqual(out["bos_rate"], 0.05, places=2)
        self.assertEqual(out["fvg_detections"], 10)          # 100/10
        self.assertEqual(out["fvg_conf_rate"], 1.0)
        self.assertTrue(out["flush_writes_file"])

    def test_02_flush_persists(self):
        out = flush_report()
        path = os.path.join(SMC_DEBUG_REPORT_DIR, out["date"] + ".json")
        self.assertTrue(os.path.exists(path))
        # cleanup
        try:
            os.remove(path)
        except OSError:
            pass

    def test_03_record_evaluation_increments(self):
        __test_reset__()
        for i in range(50):
            record_evaluation("BOS", detected=(i % 10 == 0), grade="A")
        summary = get_today_summary()
        bos = summary["primitives"]["BOS"]
        self.assertEqual(bos["total_evaluations"], 50)
        self.assertEqual(bos["detected"], 5)
        self.assertLess(bos["detection_rate"], 0.2)


def run_all():
    suite = unittest.TestLoader().loadTestsFromTestCase(SMCDiagnosticTests)
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
