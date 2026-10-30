import unittest
from unittest.mock import patch

from core.ai_v1_authority import AIV1Evidence, ai_v1_decide
from core.fer3on_decision_authority import decide_trade
from core.unified_bridge import build_decision_context, decide_and_log
from core.unified_decision import unified_decide


def _base_kwargs(**overrides):
    base = dict(
        evidence=AIV1Evidence(),
        strategy="SMC",
        signal="BUY",
        quality_score=72.0,
        confidence_pct=68.0,
        brain_score=70.0,
        execution_score=65.0,
        daily_bias="BUY",
        mtf_strength=2,
        smc_strength=5.0,
        smc_entry_confirmed=True,
        candle_trigger_confirmed=True,
        candle_weight=3,
        liquidity_alignment=70.0,
        liquidity_bias="BUY",
        structure_bias="BUY",
        sweep_probability=65.0,
        session="LONDON",
        market_regime="TRENDING",
        session_score=75.0,
        crisis_active=False,
        news_pause=False,
        risk_limits_hit=False,
        cooldown_active=False,
        market_unsafe=False,
        daily_loss_capped=False,
        emergency_stop=False,
        spread_ratio=0.10,
        atr_sufficient=True,
        rr_ratio=1.8,
        ml_score=62.0,
        ml_rl_action="PASS",
        memory_score=60.0,
        dna_score=58.0,
    )
    base.update(overrides)
    return base


class AuthorityImmutableTests(unittest.TestCase):
    def test_unified_bridge_does_not_mutate_decision(self):
        ctx = build_decision_context(
            strategy="SMC",
            signal="BUY",
            quality_score=72.0,
            confidence_pct=68.0,
            brain_score=70.0,
            execution_score=65.0,
            daily_bias="BUY",
            mtf_strength=2,
            smc_strength=5.0,
            smc_entry_confirmed=True,
            candle_trigger_confirmed=True,
            candle_weight=3,
            liquidity_alignment=70.0,
            sweep_probability=65.0,
            session="LONDON",
            market_regime="TRENDING",
            session_score=75.0,
        )
        direct = unified_decide(ctx)
        bridged = decide_and_log(ctx)
        self.assertEqual(direct.decision, bridged.decision)
        self.assertEqual(direct.size_mode, bridged.size_mode)
        self.assertAlmostEqual(direct.composite_score, bridged.composite_score, places=2)

    def test_legacy_penalties_applied_inside_unified_not_after(self):
        evidence = AIV1Evidence()
        evidence.add_legacy_rejection("FINAL_BRAIN_REJECT")
        kwargs = _base_kwargs(evidence=evidence)
        result = ai_v1_decide(**kwargs)
        self.assertIn(result.decision, {"PASS_FULL", "PASS_REDUCED", "PASS_MICRO", "HARD_BLOCK"})
        self.assertIn("legacy_net", result.debug)

    def test_ai_v1_routes_decisions_through_canonical_authority(self):
        with patch(
            "core.ai_v1_authority.decide_trade",
            wraps=decide_trade,
        ) as canonical_authority:
            result = ai_v1_decide(**_base_kwargs())

        canonical_authority.assert_called_once()
        self.assertIn(result.decision, {"PASS_FULL", "PASS_REDUCED", "PASS_MICRO", "HARD_BLOCK"})

    def test_unified_bridge_routes_decisions_through_canonical_authority(self):
        ctx = build_decision_context(
            strategy="SMC",
            signal="BUY",
            quality_score=72.0,
            confidence_pct=68.0,
            brain_score=70.0,
            execution_score=65.0,
            daily_bias="BUY",
            mtf_strength=2,
            smc_strength=5.0,
            smc_entry_confirmed=True,
            candle_trigger_confirmed=True,
            candle_weight=3,
            liquidity_alignment=70.0,
            sweep_probability=65.0,
            session="LONDON",
            market_regime="TRENDING",
            session_score=75.0,
        )
        with patch(
            "core.fer3on_decision_authority.decide_trade",
            wraps=decide_trade,
        ) as canonical_authority:
            result = decide_and_log(ctx)

        canonical_authority.assert_called_once_with(ctx)
        self.assertIn(result.decision, {"PASS_FULL", "PASS_REDUCED", "PASS_MICRO", "HARD_BLOCK"})


if __name__ == "__main__":
    unittest.main()
