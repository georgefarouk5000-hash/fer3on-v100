import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAdaptiveQualityFloor(unittest.TestCase):
    def test_reduced_execution_when_quality_is_above_minimum_floor(self):
        from core.quality_score import evaluate_quality_gate

        result = evaluate_quality_gate(
            quality_score=49,
            confidence_pct=60,
            strategy="SMC",
            session="ASIA",
            smc_entry_confirmed=True,
            candle_trigger_confirmed=True,
            sweep_probability=85,
            missed_opportunity_score=55,
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["mode"], "QUALITY_TRUST_DISABLED")
        self.assertEqual(result["threshold"], 0)
        self.assertIn("QUALITY_SCORE_INVERTED_UNCALIBRATED", result["reason"])


if __name__ == "__main__":
    unittest.main()
