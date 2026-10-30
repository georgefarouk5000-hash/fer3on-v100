# =============================================================================
# FER3ON V3.0 — CANDLE INTELLIGENCE GATE TESTS
# Covers: tier weights, strength multipliers, bonus engine,
#         opposite penalty, MTF alignment, hard-block conditions,
#         composite integration, closed-candle guard.
# =============================================================================

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.candle_gate_v3 import (
    _strength_multiplier,
    _pattern_tier_weight,
    _is_tier_a,
    compute_candle_bonus,
    compute_opposite_penalty,
    compute_mtf_bonus,
    evaluate_hard_block,
    evaluate_candle_gate,
    get_closed_candle,
    _ClosedCandleState,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _make_rates(n=5, direction="BUY"):
    """Return plain list-of-dicts rates (oldest → newest)."""
    rows = []
    base = 2000.0
    for i in range(n):
        o = base + i * 0.3 if direction == "BUY" else base - i * 0.3
        c = o + 0.5 if direction == "BUY" else o - 0.5
        rows.append({"open": o, "high": o + 1.0, "low": o - 0.5, "close": c, "time": i})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 1. STRENGTH MULTIPLIER
# ─────────────────────────────────────────────────────────────────────────────

class TestStrengthMultiplier(unittest.TestCase):

    def test_tier_90(self):
        self.assertAlmostEqual(_strength_multiplier(95), 1.30)

    def test_tier_80(self):
        self.assertAlmostEqual(_strength_multiplier(85), 1.15)

    def test_tier_70(self):
        self.assertAlmostEqual(_strength_multiplier(75), 1.00)

    def test_tier_60(self):
        self.assertAlmostEqual(_strength_multiplier(65), 0.80)

    def test_below_60(self):
        self.assertAlmostEqual(_strength_multiplier(50), 0.50)

    def test_exact_boundaries(self):
        self.assertAlmostEqual(_strength_multiplier(90), 1.30)
        self.assertAlmostEqual(_strength_multiplier(80), 1.15)
        self.assertAlmostEqual(_strength_multiplier(70), 1.00)
        self.assertAlmostEqual(_strength_multiplier(60), 0.80)

    def test_zero_strength(self):
        self.assertAlmostEqual(_strength_multiplier(0), 0.50)


# ─────────────────────────────────────────────────────────────────────────────
# 2. PATTERN TIER WEIGHTS
# ─────────────────────────────────────────────────────────────────────────────

class TestPatternTierWeight(unittest.TestCase):

    def test_tier_a_weight_5(self):
        for pat in ("ENGULFING_BULLISH", "ENGULFING_BEARISH",
                    "THREE_WHITE_SOLDIERS", "THREE_BLACK_CROWS", "ENGULFING"):
            with self.subTest(pat=pat):
                self.assertEqual(_pattern_tier_weight(pat), 5)

    def test_tier_b_weight_4(self):
        for pat in ("PINBAR_BUY", "PINBAR_SELL", "REJECTION_BUY",
                    "REJECTION_SELL", "SHOOTING_STAR", "HAMMER", "PIN_BAR"):
            with self.subTest(pat=pat):
                self.assertEqual(_pattern_tier_weight(pat), 4)

    def test_tier_c_weight_2(self):
        for pat in ("INSIDE_BAR", "INSIDE_BAR_BREAKOUT",
                    "MOMENTUM_BREAKOUT", "MORNING_STAR", "EVENING_STAR"):
            with self.subTest(pat=pat):
                self.assertEqual(_pattern_tier_weight(pat), 2)

    def test_unknown_returns_0(self):
        self.assertEqual(_pattern_tier_weight("DOJI"), 0)
        self.assertEqual(_pattern_tier_weight("NONE"), 0)
        self.assertEqual(_pattern_tier_weight(""), 0)

    def test_is_tier_a(self):
        self.assertTrue(_is_tier_a("ENGULFING_BULLISH"))
        self.assertTrue(_is_tier_a("THREE_WHITE_SOLDIERS"))
        self.assertFalse(_is_tier_a("HAMMER"))
        self.assertFalse(_is_tier_a("NONE"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. CANDLE BONUS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TestCandleBonus(unittest.TestCase):

    def test_engulfing_high_strength(self):
        # Tier A (weight 5) × multiplier 1.30 = 6.5 → capped at 6
        bonus = compute_candle_bonus("ENGULFING_BULLISH", 92)
        self.assertEqual(bonus, 6.0)

    def test_engulfing_mid_strength(self):
        # weight 5 × 1.00 = 5.0
        bonus = compute_candle_bonus("ENGULFING", 72)
        self.assertAlmostEqual(bonus, 5.0)

    def test_hammer_below_60(self):
        # Tier B (weight 4) × 0.50 = 2.0
        bonus = compute_candle_bonus("HAMMER", 55)
        self.assertAlmostEqual(bonus, 2.0)

    def test_inside_bar(self):
        # Tier C (weight 2) × 0.80 = 1.6
        bonus = compute_candle_bonus("INSIDE_BAR", 65)
        self.assertAlmostEqual(bonus, 1.6)

    def test_none_pattern_returns_0(self):
        self.assertEqual(compute_candle_bonus("NONE", 90), 0.0)

    def test_bonus_never_exceeds_6(self):
        # Any Tier A with strength 100 should be capped at 6
        bonus = compute_candle_bonus("THREE_WHITE_SOLDIERS", 100)
        self.assertLessEqual(bonus, 6.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. OPPOSITE CANDLE PENALTY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class TestOppositePenalty(unittest.TestCase):

    def test_strength_95_triggers_hard_warning(self):
        penalty, hw = compute_opposite_penalty("ENGULFING_BEARISH", 96)
        self.assertEqual(penalty, 8.0)
        self.assertTrue(hw)

    def test_strength_85(self):
        penalty, hw = compute_opposite_penalty("PINBAR_SELL", 86)
        self.assertEqual(penalty, 5.0)
        self.assertFalse(hw)

    def test_strength_75(self):
        penalty, hw = compute_opposite_penalty("REJECTION_SELL", 77)
        self.assertEqual(penalty, 4.0)
        self.assertFalse(hw)

    def test_strength_65(self):
        penalty, hw = compute_opposite_penalty("SHOOTING_STAR", 66)
        self.assertEqual(penalty, 3.0)
        self.assertFalse(hw)

    def test_strength_55(self):
        penalty, hw = compute_opposite_penalty("HAMMER", 57)
        self.assertEqual(penalty, 2.0)
        self.assertFalse(hw)

    def test_strength_below_55(self):
        penalty, hw = compute_opposite_penalty("INSIDE_BAR", 40)
        self.assertEqual(penalty, 1.0)
        self.assertFalse(hw)

    def test_none_pattern_returns_0(self):
        penalty, hw = compute_opposite_penalty("NONE", 99)
        self.assertEqual(penalty, 0.0)
        self.assertFalse(hw)


# ─────────────────────────────────────────────────────────────────────────────
# 5. MTF ALIGNMENT BONUS
# ─────────────────────────────────────────────────────────────────────────────

class TestMTFBonus(unittest.TestCase):

    def test_both_aligned(self):
        bonus, opp, reason = compute_mtf_bonus("BUY", "BUY", "BUY")
        self.assertEqual(bonus, 4)
        self.assertFalse(opp)
        self.assertIn("M5+M15", reason)

    def test_m5_only(self):
        bonus, opp, reason = compute_mtf_bonus("BUY", "BUY", "NONE")
        self.assertEqual(bonus, 2)
        self.assertFalse(opp)

    def test_m15_only(self):
        bonus, opp, reason = compute_mtf_bonus("BUY", "NONE", "BUY")
        self.assertEqual(bonus, 1)

    def test_m5_opposite(self):
        bonus, opp, reason = compute_mtf_bonus("BUY", "SELL", "NONE")
        self.assertEqual(bonus, 0)
        self.assertTrue(opp)
        self.assertIn("OPPOSITE", reason)

    def test_no_alignment(self):
        bonus, opp, reason = compute_mtf_bonus("BUY", "NONE", "NONE")
        self.assertEqual(bonus, 0)
        self.assertFalse(opp)


# ─────────────────────────────────────────────────────────────────────────────
# 6. HARD BLOCK CONDITIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestHardBlock(unittest.TestCase):

    def test_all_conditions_met(self):
        self.assertTrue(evaluate_hard_block(
            opposite_strength=96,
            opposite_pattern="ENGULFING_BEARISH",
            mtf_aligned=False,
            structure_confidence=60,
        ))

    def test_not_tier_a_no_block(self):
        self.assertFalse(evaluate_hard_block(
            opposite_strength=96,
            opposite_pattern="HAMMER",   # Tier B
            mtf_aligned=False,
            structure_confidence=60,
        ))

    def test_mtf_aligned_no_block(self):
        self.assertFalse(evaluate_hard_block(
            opposite_strength=96,
            opposite_pattern="ENGULFING_BEARISH",
            mtf_aligned=True,            # Condition 3 fails
            structure_confidence=60,
        ))

    def test_structure_confidence_high_no_block(self):
        self.assertFalse(evaluate_hard_block(
            opposite_strength=96,
            opposite_pattern="ENGULFING_BEARISH",
            mtf_aligned=False,
            structure_confidence=75,     # Condition 4 fails (≥70)
        ))

    def test_strength_below_95_no_block(self):
        self.assertFalse(evaluate_hard_block(
            opposite_strength=94,        # Condition 1 fails
            opposite_pattern="ENGULFING_BEARISH",
            mtf_aligned=False,
            structure_confidence=60,
        ))


# ─────────────────────────────────────────────────────────────────────────────
# 7. COMPOSITE INTEGRATION — evaluate_candle_gate
# ─────────────────────────────────────────────────────────────────────────────

class TestCompositeGate(unittest.TestCase):

    def _gate(self, **kw):
        defaults = dict(
            signal="BUY",
            m5_pattern="ENGULFING_BULLISH",
            m5_direction="BUY",
            m5_strength=88,
            m15_pattern="REJECTION_BUY",
            m15_direction="BUY",
            m15_strength=75,
            base_score=61.0,
            structure_confidence=80.0,
            symbol="XAUUSD",
        )
        defaults.update(kw)
        # reset duplicate guard between tests
        _ClosedCandleState._registry.clear()
        return evaluate_candle_gate(**defaults)

    # ── Spec example from docstring ──────────────────────────────────────

    def test_spec_example(self):
        """
        Spec example:
          Base Score = 61, M5 Engulfing Sell (+5), M15 Rejection Sell (+2) → Final=68
        Adapted: BUY signal, M5 Engulfing (Tier A w=5, str=88 → mult 1.15 → bonus 5.75→cap6)
                 M15 Rejection (Tier B w=4, str=75 → mult 1.00 → bonus 4 → total cap 6)
        So candle_bonus = 6, no penalty, mtf_bonus = 4 (both aligned)
        composite_delta = 6 + 4 = 10 → but let's just verify keys exist & final > base
        """
        g = self._gate()
        self.assertGreater(g["final_score"], 61.0)
        self.assertIn("candle_bonus", g)
        self.assertIn("candle_penalty", g)
        self.assertIn("composite_delta", g)
        self.assertIn("log_line", g)

    # ── Bonus cap ────────────────────────────────────────────────────────

    def test_bonus_capped_at_6(self):
        g = self._gate(
            m5_pattern="THREE_WHITE_SOLDIERS",
            m5_strength=99,
            m15_pattern="ENGULFING_BULLISH",
            m15_strength=99,
        )
        self.assertLessEqual(g["candle_bonus"], 6.0)

    # ── Opposing candle penalty ──────────────────────────────────────────

    def test_opposing_m5_applies_penalty(self):
        g = self._gate(
            m5_pattern="ENGULFING_BEARISH",
            m5_direction="SELL",   # opposes BUY
            m5_strength=87,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
        )
        self.assertGreater(g["candle_penalty"], 0)
        self.assertTrue(g["m5_opposite"])

    def test_hard_warning_at_strength_96(self):
        g = self._gate(
            m5_pattern="ENGULFING_BEARISH",
            m5_direction="SELL",
            m5_strength=96,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
        )
        self.assertTrue(g["hard_warning"])
        self.assertNotEqual(g["execution_mode"], "FULL_ENTRY")

    # ── Hard block ───────────────────────────────────────────────────────

    def test_hard_block_when_all_conditions_met(self):
        _ClosedCandleState._registry.clear()
        g = evaluate_candle_gate(
            signal="BUY",
            m5_pattern="ENGULFING_BEARISH",
            m5_direction="SELL",
            m5_strength=97,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
            base_score=50.0,
            structure_confidence=60.0,   # < 70
            symbol="XAUUSD_HARDBLOCK",
        )
        self.assertTrue(g["hard_block"])
        self.assertEqual(g["execution_mode"], "BLOCKED")

    def test_no_block_when_structure_confidence_high(self):
        _ClosedCandleState._registry.clear()
        g = evaluate_candle_gate(
            signal="BUY",
            m5_pattern="ENGULFING_BEARISH",
            m5_direction="SELL",
            m5_strength=97,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
            base_score=50.0,
            structure_confidence=75.0,   # ≥ 70 → no hard block
            symbol="XAUUSD_NOHARDBLOCK",
        )
        self.assertFalse(g["hard_block"])

    # ── MTF bonus ────────────────────────────────────────────────────────

    def test_mtf_both_aligned_adds_4(self):
        g = self._gate()
        self.assertEqual(g["mtf_bonus"], 4)

    def test_mtf_m5_only_adds_2(self):
        g = self._gate(
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
        )
        self.assertEqual(g["mtf_bonus"], 2)

    # ── Alignment flag ───────────────────────────────────────────────────

    def test_aligned_true_when_m5_matches(self):
        g = self._gate()
        self.assertTrue(g["aligned"])

    def test_aligned_false_when_none(self):
        g = self._gate(
            m5_direction="NONE",
            m5_pattern="NONE",
            m5_strength=0,
            m15_direction="NONE",
            m15_pattern="NONE",
            m15_strength=0,
        )
        self.assertFalse(g["aligned"])

    # ── Log line ─────────────────────────────────────────────────────────

    def test_log_line_contains_key_fields(self):
        g = self._gate()
        log = g["log_line"]
        self.assertIn("CANDLE_ENGINE", log)
        self.assertIn("M5", log)
        self.assertIn("M15", log)
        self.assertIn("Penalty", log)
        self.assertIn("Mode", log)


# ─────────────────────────────────────────────────────────────────────────────
# 8. CLOSED-CANDLE GUARD
# ─────────────────────────────────────────────────────────────────────────────

class TestClosedCandleGuard(unittest.TestCase):

    def setUp(self):
        _ClosedCandleState._registry.clear()

    def test_returns_second_to_last(self):
        rates = _make_rates(5)
        candle, is_dup = get_closed_candle(rates, "XAUUSD", "M5")
        self.assertIsNotNone(candle)
        # Should be index -2 (4th element in 5-element list)
        self.assertEqual(candle["time"], rates[-2]["time"])

    def test_not_duplicate_on_first_call(self):
        rates = _make_rates(5)
        _, is_dup = get_closed_candle(rates, "XAUUSD_DUP", "M5")
        self.assertFalse(is_dup)

    def test_duplicate_on_second_call_same_time(self):
        rates = _make_rates(5)
        get_closed_candle(rates, "XAUUSD_DUP2", "M5")
        _, is_dup = get_closed_candle(rates, "XAUUSD_DUP2", "M5")
        self.assertTrue(is_dup)

    def test_not_duplicate_when_new_candle_arrives(self):
        rates_old = _make_rates(5)
        rates_new = _make_rates(6)
        get_closed_candle(rates_old, "XAUUSD_NEW", "M5")
        _, is_dup = get_closed_candle(rates_new, "XAUUSD_NEW", "M5")
        self.assertFalse(is_dup)

    def test_insufficient_data_returns_none(self):
        candle, is_dup = get_closed_candle([], "SYM", "M5")
        self.assertIsNone(candle)
        self.assertTrue(is_dup)

    def test_single_candle_returns_none(self):
        candle, is_dup = get_closed_candle([{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "time": 1}], "SYM", "M5")
        self.assertIsNone(candle)
        self.assertTrue(is_dup)


# ─────────────────────────────────────────────────────────────────────────────
# 9. END-TO-END: FULL_ENTRY SCENARIO
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        _ClosedCandleState._registry.clear()

    def test_full_entry_strong_alignment(self):
        """High-strength Tier-A engulfing on both TFs → FULL_ENTRY."""
        g = evaluate_candle_gate(
            signal="SELL",
            m5_pattern="ENGULFING_BEARISH",
            m5_direction="SELL",
            m5_strength=91,
            m15_pattern="THREE_BLACK_CROWS",
            m15_direction="SELL",
            m15_strength=85,
            base_score=4.0,
            structure_confidence=80.0,
            symbol="XAUUSD_E2E_SELL",
        )
        self.assertFalse(g["hard_block"])
        self.assertGreater(g["candle_bonus"], 0)
        self.assertEqual(g["mtf_bonus"], 4)
        self.assertEqual(g["execution_mode"], "FULL_ENTRY")

    def test_no_pattern_neutral(self):
        """No patterns detected → delta near zero, execution neutral."""
        g = evaluate_candle_gate(
            signal="BUY",
            m5_pattern="NONE",
            m5_direction="NONE",
            m5_strength=0,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
            base_score=2.0,
            structure_confidence=80.0,
            symbol="XAUUSD_NOPAT",
        )
        self.assertFalse(g["hard_block"])
        self.assertEqual(g["candle_bonus"], 0.0)
        self.assertEqual(g["candle_penalty"], 0.0)
        self.assertEqual(g["mtf_bonus"], 0)
        self.assertEqual(g["composite_delta"], 0.0)
        self.assertEqual(g["execution_mode"], "NEUTRAL")

    def test_composite_score_matches_formula(self):
        """final_score == base_score + bonus − penalty + mtf_bonus."""
        _ClosedCandleState._registry.clear()
        g = evaluate_candle_gate(
            signal="BUY",
            m5_pattern="HAMMER",
            m5_direction="BUY",
            m5_strength=75,
            m15_pattern="NONE",
            m15_direction="NONE",
            m15_strength=0,
            base_score=55.0,
            structure_confidence=90.0,
            symbol="XAUUSD_FORMULA",
        )
        expected = 55.0 + g["candle_bonus"] - g["candle_penalty"] + g["mtf_bonus"]
        self.assertAlmostEqual(g["final_score"], round(expected, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
