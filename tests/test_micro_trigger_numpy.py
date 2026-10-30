# =============================================================================
# FER3ON V7 — Micro Trigger numpy.void compatibility tests
# =============================================================================

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_mt5_candles(count=6, last_tick_volume=300):
    """Simulate MT5 copy_rates_from_pos structured array."""
    dtype = [
        ("time", "i8"),
        ("open", "f8"),
        ("high", "f8"),
        ("low", "f8"),
        ("close", "f8"),
        ("tick_volume", "i8"),
        ("spread", "i4"),
        ("real_volume", "i8"),
    ]
    rows = []
    for i in range(count - 1):
        rows.append((i, 2000.0, 2001.0, 1999.0, 2000.5, 100, 2, 0))
    rows.append((count, 2000.0, 2002.0, 1999.0, 2001.0, last_tick_volume, 2, 0))
    return np.array(rows, dtype=dtype)


class TestMicroTriggerNumpy(unittest.TestCase):
    def test_candle_value_on_numpy_void(self):
        from core.micro_trigger import candle_value

        candles = _make_mt5_candles()
        last = candles[-1]
        self.assertEqual(candle_value(last, "tick_volume"), 300)
        self.assertAlmostEqual(float(candle_value(last, "close")), 2001.0)

    def test_detect_volume_spike_numpy(self):
        from core.micro_trigger import detect_volume_spike

        candles = _make_mt5_candles(last_tick_volume=350)
        self.assertTrue(detect_volume_spike(candles))

    def test_detect_volume_spike_no_attribute_error(self):
        from core.micro_trigger import detect_volume_spike

        candles = _make_mt5_candles()
        try:
            detect_volume_spike(candles)
        except AttributeError as exc:
            self.fail(f"AttributeError raised: {exc}")

    def test_evaluate_micro_triggers_numpy(self):
        from core.micro_trigger import evaluate_micro_triggers

        candles = _make_mt5_candles()
        try:
            result = evaluate_micro_triggers(candles, "BUY")
        except AttributeError as exc:
            self.fail(f"AttributeError raised: {exc}")

        self.assertIn("micro_trigger_confirmed", result)
        self.assertIn("score", result)
        self.assertIn("signals", result)

    def test_check_micro_trigger_numpy(self):
        from core.micro_trigger import check_micro_trigger

        candles = _make_mt5_candles()
        try:
            result = check_micro_trigger(candles, "BUY")
        except AttributeError as exc:
            self.fail(f"AttributeError raised: {exc}")

        self.assertIn("confirmed", result)
        self.assertIn("score", result)

    def test_dict_candles_backward_compatible(self):
        from core.micro_trigger import detect_volume_spike, evaluate_micro_triggers

        dict_candles = [
            {
                "open": 2000,
                "high": 2001,
                "low": 1999,
                "close": 2000.5,
                "tick_volume": 100,
            }
            for _ in range(5)
        ] + [
            {
                "open": 2000,
                "high": 2002,
                "low": 1999,
                "close": 2001,
                "tick_volume": 300,
            }
        ]
        self.assertTrue(detect_volume_spike(dict_candles))
        result = evaluate_micro_triggers(dict_candles, "BUY")
        self.assertIsInstance(result["score"], int)


if __name__ == "__main__":
    unittest.main()
