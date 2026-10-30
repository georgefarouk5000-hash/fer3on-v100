import unittest

from config.ai_config import AI_CONFIG
from config.execution_config import EXECUTION_CONFIG
from config.risk_config import RISK_CONFIG


class ExecutionConfigTests(unittest.TestCase):
    def test_config_layers_are_available(self):
        self.assertIsInstance(AI_CONFIG, dict)
        self.assertIsInstance(EXECUTION_CONFIG, dict)
        self.assertIsInstance(RISK_CONFIG, dict)
        self.assertIn("confidence_floor", AI_CONFIG)
        self.assertIn("max_concurrent_positions", EXECUTION_CONFIG)
        self.assertIn("max_daily_risk", RISK_CONFIG)


if __name__ == "__main__":
    unittest.main()
