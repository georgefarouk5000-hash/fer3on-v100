import unittest

from core.adaptive_sl_tp_engine import calculate_adaptive_sl_tp
from core.professional_swing_structure import (
    _label_swing_points,
    _protected_swing,
    analyze_swing_structure,
    evaluate_entry_readiness,
    select_structural_targets,
    build_swing_structure_report,
)


class ProfessionalSwingStructureTests(unittest.TestCase):
    def test_swing_labels_identify_higher_lows_and_protected_structure(self):
        highs = _label_swing_points(
            [(3, 10.0), (8, 12.0), (13, 11.0)],
            high=True,
        )
        lows = _label_swing_points(
            [(5, 7.0), (10, 8.0), (15, 8.5)],
            high=False,
        )

        self.assertEqual([point["label"] for point in highs], ["INITIAL_HIGH", "HH", "LH"])
        self.assertEqual([point["label"] for point in lows], ["INITIAL_LOW", "HL", "HL"])
        protected_low = _protected_swing(highs, lows, "BUY")
        protected_high = _protected_swing(highs, lows, "SELL")
        self.assertEqual(protected_low["price"], 8.5)
        self.assertEqual(protected_low["reason"], "LAST_CONFIRMED_HIGHER_LOW")
        self.assertEqual(protected_high["price"], 11.0)
        self.assertEqual(protected_high["reason"], "LAST_CONFIRMED_LOWER_HIGH")

    def test_structure_analysis_and_sl_tp_use_structure_context(self):
        rates = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2},
            {"open": 100.2, "high": 102.0, "low": 99.8, "close": 101.0},
            {"open": 101.0, "high": 103.0, "low": 100.2, "close": 102.0},
            {"open": 102.0, "high": 103.2, "low": 100.8, "close": 101.4},
            {"open": 101.4, "high": 102.4, "low": 98.8, "close": 99.2},
            {"open": 99.2, "high": 100.4, "low": 97.6, "close": 98.8},
            {"open": 98.8, "high": 100.6, "low": 97.0, "close": 99.6},
            {"open": 99.6, "high": 101.2, "low": 98.6, "close": 100.4},
            {"open": 100.4, "high": 103.8, "low": 99.8, "close": 103.2},
            {"open": 103.2, "high": 104.0, "low": 101.4, "close": 102.8},
            {"open": 102.8, "high": 105.0, "low": 101.8, "close": 104.4},
            {"open": 104.4, "high": 105.6, "low": 102.4, "close": 103.8},
            {"open": 103.8, "high": 106.2, "low": 102.2, "close": 104.6},
            {"open": 104.6, "high": 107.0, "low": 103.2, "close": 106.2},
            {"open": 106.2, "high": 107.4, "low": 104.2, "close": 106.8},
        ]

        analysis = analyze_swing_structure(rates, current_price=106.8)

        self.assertGreater(analysis["structure_strength"], 50)
        self.assertEqual(analysis["structure_bias"], "BUY")
        self.assertGreater(analysis["swing_high"], analysis["swing_low"])
        self.assertTrue(analysis["swing_highs"])
        self.assertTrue(analysis["swing_lows"])
        self.assertEqual(analysis["last_swing_low"], analysis["swing_lows"][-1]["price"])

        result = calculate_adaptive_sl_tp(
            atr=3.2,
            strategy="DAILY",
            lot=0.05,
            confidence=0.82,
            quality_score=84.0,
            market_regime="TRENDING",
            session="LONDON",
            structure_strength=analysis["structure_strength"] / 100.0,
            liquidity=0.76,
            volatility=0.28,
            spread=0.5,
            execution_grade="A",
            entry_price=106.8,
            signal="BUY",
            structure_analysis=analysis,
        )

        self.assertEqual(result["selected_stop_source"], "structure")
        self.assertGreaterEqual(result["sl_distance"], abs(106.8 - analysis["swing_low"]))

    def test_entry_readiness_and_structural_targets(self):
        rates = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2},
            {"open": 100.2, "high": 102.0, "low": 99.8, "close": 101.0},
            {"open": 101.0, "high": 103.0, "low": 100.2, "close": 102.0},
            {"open": 102.0, "high": 103.2, "low": 100.8, "close": 101.4},
            {"open": 101.4, "high": 102.4, "low": 98.8, "close": 99.2},
            {"open": 99.2, "high": 100.4, "low": 97.6, "close": 98.8},
            {"open": 98.8, "high": 100.6, "low": 97.0, "close": 99.6},
            {"open": 99.6, "high": 101.2, "low": 98.6, "close": 100.4},
            {"open": 100.4, "high": 103.8, "low": 99.8, "close": 103.2},
            {"open": 103.2, "high": 104.0, "low": 101.4, "close": 102.8},
            {"open": 102.8, "high": 105.0, "low": 101.8, "close": 104.4},
            {"open": 104.4, "high": 105.6, "low": 102.4, "close": 103.8},
            {"open": 103.8, "high": 106.2, "low": 102.2, "close": 104.6},
            {"open": 104.6, "high": 107.0, "low": 103.2, "close": 106.2},
            {"open": 106.2, "high": 107.4, "low": 104.2, "close": 106.8},
        ]

        analysis = analyze_swing_structure(rates, current_price=106.8)
        entry_eval = evaluate_entry_readiness(analysis, entry_price=106.8)
        self.assertTrue(entry_eval["ready"])
        self.assertTrue(any(reason in entry_eval["reasons"] for reason in {"BOS", "CHOCH", "LIQUIDITY"}))

        targets = select_structural_targets(analysis, entry_price=106.8, signal="BUY")
        self.assertGreater(len(targets), 0)
        self.assertIn("best_target", targets)
        self.assertGreater(targets["best_target"]["distance"], 0)

        report = build_swing_structure_report(analysis, entry_price=106.8, signal="BUY", stop_distance=3.2, tp_distance=9.6, final_rr=2.8)
        self.assertIn("SWING STRUCTURE REPORT", report)
        self.assertIn("Primary Trend", report)


if __name__ == "__main__":
    unittest.main()
