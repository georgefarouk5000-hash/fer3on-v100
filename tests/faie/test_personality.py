import unittest

from brain.faie.fusion import DEFAULT_WEIGHTS, EvidenceFusionEngine
from brain.faie.personality import PERSONALITY_PROFILES, get_profile
from brain.faie.chief_decision_officer import ChiefDecisionOfficer
from brain.faie.analysts import AnalystReport
from brain.faie.evidence import Evidence, BULLISH


class TestMarketPersonalityEngine(unittest.TestCase):
    def test_known_symbol_returns_its_own_profile(self):
        profile = get_profile("XAUUSD")
        self.assertEqual(profile, PERSONALITY_PROFILES["XAUUSD"])

    def test_unknown_symbol_falls_back_to_default_weights(self):
        profile = get_profile("SOME_UNLISTED_SYMBOL")
        self.assertEqual(profile, dict(DEFAULT_WEIGHTS))

    def test_lowercase_and_whitespace_symbol_still_resolves(self):
        profile = get_profile("  xauusd ")
        self.assertEqual(profile, PERSONALITY_PROFILES["XAUUSD"])

    def test_empty_or_none_symbol_does_not_raise(self):
        self.assertEqual(get_profile(""), dict(DEFAULT_WEIGHTS))
        self.assertEqual(get_profile(None), dict(DEFAULT_WEIGHTS))

    def test_returned_profile_is_a_copy_not_a_live_reference(self):
        profile = get_profile("XAUUSD")
        profile["MacroAnalyst"] = 999.0
        self.assertNotEqual(PERSONALITY_PROFILES["XAUUSD"]["MacroAnalyst"], 999.0)

    def test_every_profile_only_uses_known_analyst_names(self):
        known_analysts = {
            "MacroAnalyst", "TechnicalAnalyst", "SMCAnalyst", "LiquidityAnalyst",
            "VolumeAnalyst", "PatternAnalyst", "PsychologyAnalyst", "RiskOfficer",
            "ExecutionOfficer", "SessionAnalyst",
        }
        for symbol, profile in PERSONALITY_PROFILES.items():
            self.assertTrue(set(profile.keys()).issubset(known_analysts), symbol)

    def test_fusion_engine_accepts_a_personality_profile_directly(self):
        reports = [
            AnalystReport("SMCAnalyst", [Evidence("SMCAnalyst", "x", BULLISH, 80, 80)], bias=BULLISH),
            AnalystReport("PsychologyAnalyst", [Evidence("PsychologyAnalyst", "x", BULLISH, 80, 80)], bias=BULLISH),
        ]
        fused = EvidenceFusionEngine(weights=get_profile("XAUUSD")).fuse(reports)
        # SMCAnalyst has a much higher XAUUSD weight than PsychologyAnalyst,
        # so its normalized weight should dominate the re-normalized total.
        self.assertGreater(fused.weights_used["SMCAnalyst"], fused.weights_used["PsychologyAnalyst"])

    def test_chief_decision_officer_accepts_a_personality_profile(self):
        from core.unified_decision import DecisionContext
        ctx = DecisionContext(strategy="SMC", signal="BUY", symbol="XAUUSD", market_regime="TRENDING")
        cdo = ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))
        decision = cdo.decide(ctx)
        self.assertEqual(decision.fused_evidence.weights_used.keys() <= set(PERSONALITY_PROFILES["XAUUSD"].keys()), True)


if __name__ == "__main__":
    unittest.main()
