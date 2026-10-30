import unittest

from tools.system_health_check import run_health_check


class SystemHealthCheckTests(unittest.TestCase):
    def test_health_check_returns_score_and_summary(self):
        result = run_health_check()
        self.assertIn("score", result)
        self.assertIn("summary", result)
        self.assertIn("checks", result)
        self.assertIsInstance(result["score"], int)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()
