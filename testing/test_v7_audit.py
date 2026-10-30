import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestV7Audit(unittest.TestCase):
    def test_run_v7_audit_returns_complete_report(self):
        from core.v7_audit import run_v7_audit

        report = run_v7_audit()

        self.assertIn("results", report)
        self.assertEqual(report["summary"]["total"], 7)
        self.assertEqual(report["summary"]["passed"], report["summary"]["total"])
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["health_score"], 100)


if __name__ == "__main__":
    unittest.main()
