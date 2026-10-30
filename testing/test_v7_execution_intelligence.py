# =============================================================================
# FER3ON V7 — Unit tests (no MT5 required)
# =============================================================================

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDynamicConfidence(unittest.TestCase):
    def test_london_threshold(self):
        from core.dynamic_confidence import get_dynamic_confidence_threshold

        r = get_dynamic_confidence_threshold("LONDON", "TRENDING", hour=10)
        self.assertEqual(r["base"], 52)
        self.assertEqual(r["threshold"], 52)

    def test_volatile_adjustment(self):
        from core.dynamic_confidence import get_dynamic_confidence_threshold

        r = get_dynamic_confidence_threshold("LONDON", "VOLATILE", hour=10)
        self.assertEqual(r["threshold"], 57)

    def test_overlap_threshold(self):
        from core.dynamic_confidence import get_dynamic_confidence_threshold

        r = get_dynamic_confidence_threshold("NEWYORK", "TRENDING", hour=14)
        self.assertTrue(r["overlap"])
        self.assertEqual(r["threshold"], 50)


class TestVelocityEngine(unittest.TestCase):
    def test_classify_velocity(self):
        from core.velocity_engine import classify_velocity, compute_velocity

        self.assertEqual(classify_velocity(0.5), "WEAK")
        self.assertEqual(classify_velocity(1.0), "NORMAL")
        self.assertEqual(classify_velocity(1.5), "STRONG")
        self.assertEqual(classify_velocity(2.0), "EXPLOSIVE")

    def test_velocity_formula(self):
        from core.velocity_engine import compute_velocity

        self.assertAlmostEqual(compute_velocity(2010, 2000, 10), 1.0)


class TestConfidenceDecay(unittest.TestCase):
    def test_decay_steps(self):
        from core.confidence_decay import apply_confidence_decay

        r = apply_confidence_decay(72, elapsed_seconds=300, atr=3.0, session="LONDON")
        self.assertLess(r["decayed_confidence"], 72)
        self.assertGreaterEqual(r["decayed_confidence"], 60)


class TestMissedOpportunity(unittest.TestCase):
    def test_directional_move_buy(self):
        from core.missed_opportunity import _directional_move, classify_rejection_outcome

        move = _directional_move(2000, 2015, "BUY")
        self.assertEqual(move, 15)
        self.assertEqual(classify_rejection_outcome(move), "FALSE_REJECTION")

    def test_missed_opportunity_score(self):
        from core.missed_opportunity import compute_missed_opportunity_score

        score = compute_missed_opportunity_score(
            {"total_rejections": 10, "false_rejections": 2}
        )
        self.assertEqual(score, 80.0)


class TestOpportunityEngine(unittest.TestCase):
    def test_classify_entry_bands(self):
        from brain.opportunity_engine import classify_opportunity_entry

        self.assertEqual(classify_opportunity_entry(58), "ENTER_QUARTER")
        self.assertEqual(classify_opportunity_entry(70), "ENTER_HALF")
        self.assertEqual(classify_opportunity_entry(85), "NONE")
        self.assertEqual(classify_opportunity_entry(50), "ENTER_QUARTER")

    def test_evaluate_blocked_by_mtf(self):
        from brain.opportunity_engine import evaluate_opportunity

        r = evaluate_opportunity(
            signal="BUY",
            confidence_pct=72,
            mtf_direction="SELL",
            liquidity_bias="BUY",
            session="LONDON",
            market_regime="TRENDING",
        )
        self.assertEqual(r["action"], "NONE")
        self.assertEqual(r["reason"], "MTF_NOT_ALIGNED")

    def test_evaluate_quarter_at_55(self):
        from brain.opportunity_engine import evaluate_opportunity

        r = evaluate_opportunity(
            signal="BUY",
            confidence_pct=58,
            mtf_direction="BUY",
            liquidity_bias="BUY",
            session="LONDON",
            market_regime="TRENDING",
        )
        self.assertEqual(r["action"], "ENTER_QUARTER")
        self.assertEqual(r["lot_mult"], 0.25)


class TestScaleIn(unittest.TestCase):
    def test_confidence_to_scale(self):
        from execution.scale_in import confidence_to_scale_pct

        self.assertEqual(confidence_to_scale_pct(60), 0.25)
        self.assertEqual(confidence_to_scale_pct(70), 0.50)
        self.assertEqual(confidence_to_scale_pct(80), 0.75)
        self.assertEqual(confidence_to_scale_pct(90), 1.00)

    def test_no_scale_when_losing(self):
        from execution.scale_in import evaluate_scale_in

        class Pos:
            type = 0
            price_open = 2010
            volume = 0.10

        r = evaluate_scale_in(Pos(), current_price=2005, confidence_score=80)
        self.assertFalse(r["approved"])
        self.assertEqual(r["reason"], "NOT_IN_PROFIT")


class TestMicroTrigger(unittest.TestCase):
    def test_rejection_candle_buy(self):
        from core.micro_trigger import detect_rejection_candle

        candle = {
            "open": 2001,
            "high": 2002,
            "low": 1995,
            "close": 2000,
        }
        self.assertTrue(detect_rejection_candle([candle], "BUY"))

    def test_candle_value_numpy_void(self):
        import numpy as np
        from core.micro_trigger import candle_value, detect_volume_spike

        dtype = [("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")]
        rows = np.array(
            [(1, 2, 0.5, 1.5, 100)] * 5 + [(1, 2, 0.5, 1.5, 300)],
            dtype=dtype,
        )
        self.assertEqual(candle_value(rows[-1], "tick_volume"), 300)
        self.assertTrue(detect_volume_spike(rows))

    def test_micro_trigger_error_safe(self):
        from core.micro_trigger import check_micro_trigger

        r = check_micro_trigger(None, "BUY")
        self.assertIn("score", r)
        self.assertIn("confirmed", r)


class TestLiquidityVacuum(unittest.TestCase):
    def test_vacuum_score_bounded(self):
        from core.liquidity_vacuum import compute_vacuum_score

        candles = [
            {"open": 2000, "high": 2001, "low": 1999, "close": 2000.5}
            for _ in range(10)
        ]
        closes = [2000 + i * 0.5 for i in range(10)]
        score = compute_vacuum_score(candles, closes, atr=2.0)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class TestSweepPredictor(unittest.TestCase):
    def test_sweep_probability_range(self):
        from core.sweep_predictor import compute_sweep_probability

        r = compute_sweep_probability(
            signal="BUY",
            equal_highs=[],
            equal_lows=[1995.0],
            liquidity_pools=[],
            current_price=2000.0,
            session="LONDON",
        )
        self.assertGreaterEqual(r["sweep_probability"], 0)
        self.assertLessEqual(r["sweep_probability"], 100)


class TestBrainUnifiedV7(unittest.TestCase):
    def test_v7_bonus_lowers_reject(self):
        from core.brain_unified import compute_final_brain_score

        base = compute_final_brain_score(
            master_score=50,
            confidence_pct=50,
            quality_score=50,
            exec_grade="B",
            reject_floor=54,
            wait_floor=54,
        )
        boosted = compute_final_brain_score(
            master_score=50,
            confidence_pct=50,
            quality_score=50,
            exec_grade="B",
            v7_bonus=8,
            reject_floor=48,
            wait_floor=54,
        )
        self.assertGreater(boosted["final_score"], base["final_score"])


if __name__ == "__main__":
    unittest.main()
