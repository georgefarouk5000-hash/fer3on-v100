import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAdaptiveArchitecture(unittest.TestCase):
    def test_candle_thresholds_accept_confirmed_smc_signal(self):
        from core.candle_trigger import _aggregate_weights

        confirmed, weight, reasons, score = _aggregate_weights(
            "BUY",
            ("MOMENTUM_BREAKOUT", "BUY", 2, 72),
            ("NONE", "NONE", 0, 0),
            strategy="SMC",
        )

        self.assertTrue(confirmed)
        self.assertGreaterEqual(weight, 1)
        self.assertGreaterEqual(score, 1.2)

    def test_ai_override_reduces_conflict_penalty(self):
        from core.brain_unified import compute_final_brain_score

        report = compute_final_brain_score(
            72,
            85,
            74,
            "A",
            ml_score=95,
            candle_weight=2,
            conflict_report={"aligned_count": 1, "opposed_count": 2},
            strategy="SMC",
            ai_override=True,
        )

        self.assertTrue(report["ai_override_applied"])
        self.assertLess(report["conflict_penalty"], 3.0)

    def test_quality_gate_allows_ai_bypass_for_smc(self):
        from core.quality_score import evaluate_quality_gate

        result = evaluate_quality_gate(
            47,
            confidence_pct=85,
            strategy="SMC",
            ml_score=90,
            session="ASIA",
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["mode"], "QUALITY_TRUST_DISABLED")
        self.assertEqual(result["risk_multiplier"], 1.00)

    def test_trade_dna_scoring_uses_multiple_metrics(self):
        from brain.trade_dna import calculate_trade_dna_score

        trades = [
            {"result": "WIN", "profit": 120.0, "quality_score": 80, "confidence_pct": 70},
            {"result": "WIN", "profit": 90.0, "quality_score": 82, "confidence_pct": 73},
            {"result": "LOSS", "profit": -40.0, "quality_score": 60, "confidence_pct": 65},
            {"result": "WIN", "profit": 60.0, "quality_score": 78, "confidence_pct": 72},
            {"result": "WIN", "profit": 100.0, "quality_score": 84, "confidence_pct": 75},
        ]

        score = calculate_trade_dna_score(trades)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertGreater(score, 50)

    def test_testing_mode_uses_requested_risk_multipliers(self):
        from core.quality_score import evaluate_quality_gate
        from core.settings import TESTING_MODE_RISK_MULTIPLIERS

        self.assertEqual(TESTING_MODE_RISK_MULTIPLIERS["MICRO"], 0.50)
        self.assertEqual(TESTING_MODE_RISK_MULTIPLIERS["REDUCED"], 0.75)
        self.assertEqual(TESTING_MODE_RISK_MULTIPLIERS["NORMAL"], 1.00)

        result = evaluate_quality_gate(
            45,
            confidence_pct=40,
            strategy="SMC",
            ml_score=90,
            session="ASIA",
        )

        self.assertTrue(result["approved"])
        self.assertEqual(result["mode"], "QUALITY_TRUST_DISABLED")
        self.assertEqual(result["risk_multiplier"], 1.00)

    def test_trade_dna_formula_uses_requested_components(self):
        from brain.trade_dna import calculate_trade_dna_score

        trades = [
            {"result": "WIN", "profit": 100.0, "quality_score": 0, "confidence_pct": 0},
            {"result": "LOSS", "profit": -50.0, "quality_score": 0, "confidence_pct": 0},
        ]

        score = calculate_trade_dna_score(trades)

        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 100.0)
        self.assertGreater(score, 50.0)

    def test_reinforcement_state_and_reward_support_extra_features(self):
        from ml.reinforcement import compute_reward, encode_state

        state = encode_state(
            "VOLATILE",
            "LONDON",
            88,
            3,
            True,
            18,
            spread_band="WIDE",
            atr_band="HIGH",
            volatility_band="HIGH",
            sweep_detected=True,
            volume_spike=True,
            micro_breakout=True,
            drawdown_state="LOW",
            session_killzone="LONDON",
            execution_latency="LOW",
            news_impact="LOW",
        )
        reward = compute_reward(
            "WIN",
            140,
            2.0,
            88,
            "A+",
            recovery_speed=0.8,
            drawdown_control=0.7,
            win_streak_bonus=0.4,
        )

        self.assertIn("VL", state)
        self.assertGreater(reward, 2.0)

    def test_market_snapshot_hash_accepts_numpy_like_rates(self):
        import numpy as np

        import main

        rates = np.array(
            [{"close": 1.2345}, {"close": 1.2346}, {"close": 1.2347}],
            dtype=object,
        )

        snapshot_hash = main.build_market_snapshot_hash(rates, 0.1234, "RANGING", "ASIA", 70)

        self.assertIsNotNone(snapshot_hash)

    def test_gbm_predictor_handles_incompatible_model_artifacts(self):
        from ml.xgboost_model import GBMPredictor

        predictor = GBMPredictor()

        self.assertFalse(predictor.trained)
        self.assertEqual(predictor.engine, "NONE")

    def test_ml_status_manager_reports_incomplete_model_state(self):
        from core.ml_status_manager import build_ml_status_report

        report = build_ml_status_report(model_files=[], feature_count=22, training_trades=0)

        self.assertEqual(report["status"], "DISABLED")
        self.assertEqual(report["confidence_source"], "FALLBACK")

    def test_trade_dna_display_uses_learning_mode_for_new_accounts(self):
        from brain.trade_dna import get_trade_dna_display

        self.assertEqual(get_trade_dna_display(5, 0), "LEARNING")
        self.assertEqual(get_trade_dna_display(25, 72), "72")


if __name__ == "__main__":
    unittest.main()
