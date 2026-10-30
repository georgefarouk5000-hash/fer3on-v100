import unittest
from unittest.mock import patch

from core.adaptive_sl_tp_engine import calculate_adaptive_sl_tp


class AdaptiveSLTPEngineTests(unittest.TestCase):
    def test_fixed_atr_mode_uses_strategy_profiles_and_ignores_structure(self):
        with patch("core.adaptive_sl_tp_engine.SLTP_MODE", "FIXED_ATR"):
            result = calculate_adaptive_sl_tp(
                atr=10.0,
                strategy="SMC",
                confidence=1.0,
                market_regime="TRENDING",
                min_sl=5.0,
                entry_price=2000.0,
                signal="BUY",
                structure_analysis={
                    "swing_low": 1990.0,
                    "swing_high": 2050.0,
                },
            )

        self.assertTrue(result["stop_valid"])
        self.assertEqual(result["sltp_mode"], "FIXED_ATR")
        self.assertEqual(result["selected_stop_source"], "fixed_atr")
        self.assertEqual(result["sl_distance"], 12.0)
        self.assertAlmostEqual(result["tp_distance"], 25.0)
        self.assertEqual(result["risk_reward"], 2.08)
        self.assertEqual(result["target_source"], "rr_fallback")
        self.assertIsNone(result["target_price"])

    def test_adaptive_mode_remains_default_behavior(self):
        with patch("core.adaptive_sl_tp_engine.SLTP_MODE", "ADAPTIVE"):
            result = calculate_adaptive_sl_tp(
                atr=10.0,
                strategy="SMC",
                confidence=1.0,
                market_regime="TRENDING",
                min_sl=5.0,
                entry_price=2000.0,
                signal="BUY",
                structure_analysis={"swing_low": 1990.0},
            )

        self.assertEqual(result["sltp_mode"], "ADAPTIVE")
        self.assertEqual(result["selected_stop_source"], "structure")

    def test_sl_and_tp_change_with_atr_and_lot(self):
        base = calculate_adaptive_sl_tp(
            atr=12.0,
            strategy="SMC",
            lot=0.01,
            confidence=0.55,
            quality_score=60.0,
            market_regime="RANGING",
            session="LONDON",
            structure_strength=0.6,
            liquidity=0.55,
            volatility=0.4,
            spread=1.0,
            execution_grade="B",
        )
        larger = calculate_adaptive_sl_tp(
            atr=24.0,
            strategy="SMC",
            lot=0.10,
            confidence=0.55,
            quality_score=60.0,
            market_regime="RANGING",
            session="LONDON",
            structure_strength=0.6,
            liquidity=0.55,
            volatility=0.4,
            spread=1.0,
            execution_grade="B",
        )

        self.assertGreater(larger["sl_distance"], base["sl_distance"])
        self.assertGreater(larger["tp_distance"], base["tp_distance"])
        self.assertGreater(larger["risk_reward"], base["risk_reward"])

    def test_quality_and_regime_change_sl_and_rr(self):
        conservative = calculate_adaptive_sl_tp(
            atr=15.0,
            strategy="SMC",
            lot=0.02,
            confidence=0.45,
            quality_score=45.0,
            market_regime="CRISIS",
            session="ASIA",
            structure_strength=0.35,
            liquidity=0.25,
            volatility=0.7,
            spread=3.0,
            execution_grade="C",
        )
        premium = calculate_adaptive_sl_tp(
            atr=15.0,
            strategy="SMC",
            lot=0.02,
            confidence=0.85,
            quality_score=90.0,
            market_regime="TRENDING",
            session="LONDON",
            structure_strength=0.9,
            liquidity=0.85,
            volatility=0.25,
            spread=0.5,
            execution_grade="A",
        )

        self.assertNotEqual(conservative["sl_distance"], premium["sl_distance"])
        self.assertNotEqual(conservative["risk_reward"], premium["risk_reward"])

    def test_structure_context_can_override_atr_distance(self):
        result = calculate_adaptive_sl_tp(
            atr=8.0,
            strategy="SMC",
            lot=0.02,
            confidence=0.8,
            quality_score=85.0,
            market_regime="TRENDING",
            session="LONDON",
            structure_strength=0.85,
            liquidity=0.8,
            volatility=0.25,
            spread=0.5,
            execution_grade="A",
            entry_price=2000.0,
            signal="BUY",
            structure_context={
                "swing_high": 2025.0,
                "swing_low": 1990.0,
            },
        )
        self.assertTrue(result["stop_valid"])
        self.assertEqual(result["selected_stop_source"], "structure")
        self.assertAlmostEqual(
            result["sl_distance"],
            2000.0 - (1990.0 - result["structure_buffer"]),
            places=2,
        )
        self.assertEqual(result["target_source"], "structure")
        self.assertEqual(result["target_price"], 2025.0)

    def test_structure_level_on_wrong_side_is_not_used_as_stop(self):
        result = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="SMC",
            market_regime="TRENDING",
            min_sl=5.0,
            entry_price=2000.0,
            signal="BUY",
            structure_analysis={"swing_low": 2001.0, "swing_high": 2010.0},
        )
        self.assertEqual(result["selected_stop_source"], "atr")
        self.assertTrue(result["stop_valid"])
        self.assertNotEqual(result["target_source"], "structure")

    def test_protected_swing_is_selected_and_recorded_as_stop_anchor(self):
        result = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="SMC",
            market_regime="TRENDING",
            min_sl=5.0,
            entry_price=2000.0,
            signal="BUY",
            structure_analysis={
                "swing_lows": [
                    {"index": 10, "price": 1998.0, "label": "HL"},
                    {"index": 20, "price": 1997.0, "label": "HL"},
                ],
                "swing_high": 2020.0,
                "protected_low": {
                    "index": 20,
                    "price": 1997.0,
                    "label": "HL",
                    "kind": "protected_low",
                    "reason": "LAST_CONFIRMED_HIGHER_LOW",
                },
            },
        )

        self.assertEqual(result["selected_stop_source"], "structure")
        self.assertEqual(result["selected_swing"], 1997.0)
        self.assertEqual(result["selected_stop_anchor"]["index"], 20)
        self.assertEqual(result["selected_stop_anchor"]["label"], "HL")
        self.assertEqual(
            result["stop_selection_reason"],
            "LAST_CONFIRMED_HIGHER_LOW",
        )

    def test_protected_swing_outside_cap_uses_nearer_confirmed_swing(self):
        result = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="SMC",
            market_regime="TRENDING",
            max_sl=100.0,
            min_sl=5.0,
            entry_price=2000.0,
            signal="BUY",
            structure_analysis={
                "swing_lows": [
                    {"index": 10, "price": 1998.0, "label": "HL"},
                    {"index": 20, "price": 1700.0, "label": "HL"},
                ],
                "protected_low": {
                    "index": 20,
                    "price": 1700.0,
                    "label": "HL",
                    "kind": "protected_low",
                    "reason": "LAST_CONFIRMED_HIGHER_LOW",
                },
            },
        )

        self.assertEqual(result["selected_swing"], 1998.0)
        self.assertIn("USE_NEAREST_CONFIRMED_SWING", result["stop_selection_reason"])

    def test_stop_rejected_when_broker_minimum_exceeds_policy_cap(self):
        result = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="SMC",
            confidence=0.5,
            market_regime="RANGING",
            broker_stop_level=20.0,
            min_sl=5.0,
            entry_price=2000.0,
            signal="BUY",
            structure_analysis={"swing_low": 1990.0},
        )
        self.assertFalse(result["stop_valid"])
        self.assertEqual(result["stop_reason"], "BROKER_MINIMUM_EXCEEDS_SL_CAP")

    def test_adaptive_sl_tp_returns_tp_tiers(self):
        result = calculate_adaptive_sl_tp(
            atr=10.0,
            strategy="SMC",
            lot=0.02,
            confidence=0.7,
            quality_score=75.0,
            market_regime="RANGING",
            session="LONDON",
            structure_strength=0.5,
            liquidity=0.6,
            volatility=0.4,
            spread=1.5,
            execution_grade="B",
            entry_price=2000.0,
            signal="BUY",
        )
        self.assertIn("tp_tiers", result)
        self.assertEqual(len(result["tp_tiers"]), 3)
        first_tier = result["tp_tiers"][0]
        self.assertEqual(first_tier["label"], "TP1")
        from core.settings import MULTI_TP_PROFILE
        self.assertEqual(first_tier["close_pct"], MULTI_TP_PROFILE["SMC"]["tp1_pct"])
        self.assertGreater(first_tier["price"], 2000.0)

    def test_broker_stop_level_is_guard_not_primary_basis(self):
        computed = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="MICRO",
            lot=0.01,
            confidence=0.6,
            quality_score=70.0,
            market_regime="RANGING",
            session="LONDON",
            structure_strength=0.6,
            liquidity=0.6,
            volatility=0.3,
            spread=1.0,
            execution_grade="B",
            broker_stop_level=0,
            broker_stop_fallback=200,
            min_sl=0,
        )
        guarded = calculate_adaptive_sl_tp(
            atr=5.0,
            strategy="MICRO",
            lot=0.01,
            confidence=0.6,
            quality_score=70.0,
            market_regime="RANGING",
            session="LONDON",
            structure_strength=0.6,
            liquidity=0.6,
            volatility=0.3,
            spread=1.0,
            execution_grade="B",
            broker_stop_level=120,
            broker_stop_fallback=200,
            min_sl=0,
        )

        self.assertLess(computed["sl_distance"], 200)
        self.assertGreaterEqual(guarded["sl_distance"], 120)


if __name__ == "__main__":
    unittest.main()
