import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mt5_compat
from core.mt5_compat import MT5_AVAILABLE, mt5, connect_mt5, copy_rates_safe


class TestMt5Compat(unittest.TestCase):
    def test_real_mt5_without_required_api_falls_back_to_stub(self):
        required_api = {"initialize", "account_info", "terminal_info", "copy_rates_from_pos"}
        if all(hasattr(mt5_compat.mt5, name) for name in required_api):
            self.skipTest("Real MetaTrader5 API is available; no fallback needed")

        self.assertFalse(mt5_compat.MT5_AVAILABLE)
        self.assertTrue(getattr(mt5_compat.mt5, "is_stub", False))
        self.assertTrue(mt5_compat.connect_mt5())

    def test_stub_mode_initializes_without_real_mt5(self):
        if MT5_AVAILABLE:
            self.skipTest("Real MetaTrader5 package is installed; skipping stub-mode regression test")

        self.assertTrue(connect_mt5())
        self.assertTrue(mt5.terminal_info().connected)
        self.assertTrue(mt5.shutdown())

    def test_copy_rates_safe_returns_none_when_mt5_unavailable(self):
        self.assertIsNone(copy_rates_safe("EURUSD", 5, 0, 10))


if __name__ == "__main__":
    unittest.main()
