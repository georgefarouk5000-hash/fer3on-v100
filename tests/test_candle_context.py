# =============================================================================
# FER3ON V6 — Candle context engine tests
# =============================================================================

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_candles(n=20, direction="BUY"):
    dtype = [("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8")]
    rows = []
    base = 2000.0
    for i in range(n):
        if direction == "BUY":
            o = base + i * 0.3
            c = o + 0.5
        else:
            o = base - i * 0.3
            c = o - 0.5
        rows.append((o, o + 1.0, o - 0.5, c))
    return np.array(rows, dtype=dtype)


class TestCandleContext(unittest.TestCase):
    def test_score_bounded(self):
        from core.candle_context import compute_candle_context_score

        score = compute_candle_context_score(_make_candles(20, "BUY"), "BUY")
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_analyze_returns_bonus(self):
        from core.candle_context import analyze_candle_context

        result = analyze_candle_context(_make_candles(20, "BUY"), "BUY")
        self.assertIn("candle_context_score", result)
        self.assertIn("confidence_bonus", result)

    def test_dict_candles(self):
        from core.candle_context import analyze_candle_context

        candles = [
            {"open": 2000, "high": 2001, "low": 1999, "close": 2000.5}
            for _ in range(15)
        ]
        result = analyze_candle_context(candles, "BUY")
        self.assertTrue(result["enabled"])


if __name__ == "__main__":
    unittest.main()
