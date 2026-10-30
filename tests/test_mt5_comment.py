# =============================================================================
# FER3ON V6 — MT5 comment sanitization tests
# =============================================================================

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMt5Comment(unittest.TestCase):
    def test_sanitize_max_length(self):
        from core.mt5_order_utils import sanitize_mt5_comment

        long = "FER3ON_V6_SMC_B_EX2_BALANCED_ENTER_QUARTER"
        out = sanitize_mt5_comment(long)
        self.assertLessEqual(len(out), 30)
        self.assertTrue(out.isascii())

    def test_compact_comment(self):
        from core.mt5_order_utils import build_compact_order_comment

        c = build_compact_order_comment("SMC", "B")
        self.assertEqual(c, "F6_SMC_B")
        self.assertLessEqual(len(c), 30)

    def test_strips_invalid_chars(self):
        from core.mt5_order_utils import sanitize_mt5_comment

        out = sanitize_mt5_comment("F6_SMC_A+ test!")
        self.assertNotIn(" ", out)
        self.assertNotIn("+", out)
        self.assertTrue(out.startswith("F6_SMC_A"))

    def test_prepare_order_comment(self):
        from core.mt5_order_utils import prepare_order_comment

        req = {"comment": "X" * 50}
        prepare_order_comment(req)
        self.assertLessEqual(len(req["comment"]), 30)


if __name__ == "__main__":
    unittest.main()
