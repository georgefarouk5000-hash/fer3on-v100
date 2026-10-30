import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.v7_validator import run_v7_deep_validation


class TestV7DeepValidation(unittest.TestCase):
    def test_v7_deep_validation_suite(self):
        report = run_v7_deep_validation()

        self.assertIn("results", report)
        self.assertEqual(report["summary"]["total"], 7)
        self.assertEqual(report["summary"]["passed"], 7)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["summary"]["functional_score"], 7)
        self.assertGreaterEqual(report["summary"]["coverage_percentage"], 100.0)


if __name__ == "__main__":
    unittest.main()
