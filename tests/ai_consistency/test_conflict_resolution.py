import unittest

from core.conflict_resolution import resolve_conflicting_signals


class ConflictResolutionTests(unittest.TestCase):
    def test_conflicting_signals_are_weighted_and_bounded(self):
        result = resolve_conflicting_signals(
            ai_score=0.92,
            structure_score=0.30,
            execution_score=0.65,
            risk_score=0.20,
        )
        self.assertIn("final_score", result)
        self.assertIn("decision", result)
        self.assertGreaterEqual(result["final_score"], 0.0)
        self.assertLessEqual(result["final_score"], 1.0)
        self.assertIn(result["decision"], {"approve", "hold", "reject"})


if __name__ == "__main__":
    unittest.main()
