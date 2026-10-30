import unittest

from brain.faie.analysts import SessionAnalyst, DEFAULT_ANALYSTS
from brain.faie.evidence import NEUTRAL
from brain.faie.fusion import DEFAULT_WEIGHTS
from brain.faie.personality import PERSONALITY_PROFILES, get_profile
from core.unified_decision import DecisionContext


class TestSessionAnalystRegistration(unittest.TestCase):
    def test_session_analyst_is_in_default_analysts(self):
        names = [a.name for a in DEFAULT_ANALYSTS]
        self.assertIn("SessionAnalyst", names)

    def test_session_analyst_has_a_default_weight(self):
        self.assertIn("SessionAnalyst", DEFAULT_WEIGHTS)
        self.assertGreater(DEFAULT_WEIGHTS["SessionAnalyst"], 0.0)

    def test_default_weights_still_sum_to_one(self):
        self.assertAlmostEqual(sum(DEFAULT_WEIGHTS.values()), 1.0, places=6)

    def test_every_personality_profile_has_session_analyst_and_sums_to_one(self):
        for symbol, profile in PERSONALITY_PROFILES.items():
            self.assertIn("SessionAnalyst", profile, symbol)
            self.assertAlmostEqual(sum(profile.values()), 1.0, places=6, msg=symbol)


class TestSessionAnalystWithRealHour(unittest.TestCase):
    def test_real_hour_produces_a_fine_grained_phase_tag(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", hour=9, minute=15)
        report = SessionAnalyst().analyze(ctx)
        self.assertFalse(report.partial)
        self.assertEqual(len(report.evidence), 1)
        ev = report.evidence[0]
        self.assertIn("london_sweep", ev.tags)
        self.assertIn("liquidity_window", ev.tags)
        self.assertEqual(ev.direction, NEUTRAL)
        self.assertNotIn("coarse fallback", ev.source)

    def test_off_hours_is_flagged_as_a_weak_window(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", hour=20, minute=0)
        report = SessionAnalyst().analyze(ctx)
        self.assertIn("WEAK window", report.notes)

    def test_bias_is_always_neutral_never_directional(self):
        # Liquidity window strength is not a market lean — see module
        # docstring in brain/faie/analysts.py. Must stay NEUTRAL regardless
        # of how strong/weak the window is.
        for hour in range(24):
            ctx = DecisionContext(strategy="SMC", signal="BUY", hour=hour)
            report = SessionAnalyst().analyze(ctx)
            self.assertEqual(report.bias, NEUTRAL, f"hour={hour}")

    def test_evidence_never_moves_fused_net_score(self):
        # NEUTRAL-direction evidence must contribute exactly 0 to the
        # analyst's own net_score (weighted_score sign table) — this is
        # intentional (see analysts.py docstring), not a bug to "fix".
        ctx = DecisionContext(strategy="SMC", signal="BUY", hour=9, minute=15)
        report = SessionAnalyst().analyze(ctx)
        net = sum(e.weighted_score for e in report.evidence) / len(report.evidence)
        self.assertEqual(net, 0.0)


class TestSessionAnalystWithoutRealHour(unittest.TestCase):
    def test_missing_hour_falls_back_to_coarse_session_mapping(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", session="LONDON")
        report = SessionAnalyst().analyze(ctx)
        self.assertFalse(report.partial)
        ev = report.evidence[0]
        self.assertIn("coarse fallback", ev.source)
        self.assertIn("(degraded coarse read", report.notes)

    def test_coarse_fallback_has_lower_confidence_than_real_hour_read(self):
        ctx_real = DecisionContext(strategy="SMC", signal="BUY", hour=9, minute=0)
        ctx_coarse = DecisionContext(strategy="SMC", signal="BUY", session="ASIA")
        real_conf = SessionAnalyst().analyze(ctx_real).evidence[0].confidence
        coarse_conf = SessionAnalyst().analyze(ctx_coarse).evidence[0].confidence
        self.assertLess(coarse_conf, real_conf)

    def test_unknown_session_falls_back_to_off_hours_not_a_crash(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", session="UNKNOWN")
        report = SessionAnalyst().analyze(ctx)
        self.assertIn("phase=OFF_HOURS", report.notes)

    def test_never_guesses_now_for_a_historical_context(self):
        # This is the core honesty guarantee: with no ctx.hour, the source
        # string must never claim a real detect_session_phase(hour, ...)
        # read happened.
        ctx = DecisionContext(strategy="SMC", signal="SELL", session="NEW_YORK")
        report = SessionAnalyst().analyze(ctx)
        for ev in report.evidence:
            self.assertNotIn("ctx.hour, ctx.minute", ev.source)


class TestSessionAnalystIntegration(unittest.TestCase):
    def test_chief_decision_officer_runs_with_session_analyst_included(self):
        from brain.faie.chief_decision_officer import ChiefDecisionOfficer
        ctx = DecisionContext(strategy="SMC", signal="BUY", symbol="XAUUSD", hour=9, minute=30)
        cdo = ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))
        decision = cdo.decide(ctx)
        self.assertIn("SessionAnalyst", decision.fused_evidence.per_analyst)

    def test_backtest_harness_still_works_with_no_hour_on_historical_rows(self):
        from testing.faie_backtest import _row_to_decision_context
        row = {
            "signal": "BUY", "strategy": "SMC", "session": "LONDON",
            "market_regime": "TRENDING", "result": "WIN", "profit": "10",
        }
        ctx = _row_to_decision_context(row)
        self.assertIsNotNone(ctx)
        self.assertIsNone(ctx.hour)


if __name__ == "__main__":
    unittest.main()
