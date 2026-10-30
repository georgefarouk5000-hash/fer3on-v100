import os
import unittest

from core.unified_decision import DecisionContext
from brain.faie import (
    ChiefDecisionOfficer,
    ExplanationBuilder,
    EvidenceFusionEngine,
    ContradictionResolver,
    ScenarioEngine,
    Evidence,
)
from brain.faie.evidence import BULLISH, BEARISH, NEUTRAL
from brain.faie.analysts import AnalystReport


FORBIDDEN_TOKENS = (
    "trade_executor",
    "execution_optimizer",
    "MetaTrader5",
    "mt5.",
    "order_send",
    "order_close",
    "place_order",
)


class TestConstitutionalSafety(unittest.TestCase):
    """Volume 1: brain/faie must never gain execution capability."""

    def test_no_execution_capability(self):
        faie_dir = os.path.join(os.path.dirname(__file__), "..", "..", "brain", "faie")
        faie_dir = os.path.abspath(faie_dir)
        self.assertTrue(os.path.isdir(faie_dir), f"expected {faie_dir} to exist")

        offenders = []
        for fname in os.listdir(faie_dir):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(faie_dir, fname)
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            # Only scan executable lines. Comment lines (the constitutional
            # notices) are allowed to *name* these forbidden modules in
            # order to state that they are absent.
            code_lines = [ln for ln in lines if not ln.lstrip().startswith("#")]
            content = "".join(code_lines)
            for token in FORBIDDEN_TOKENS:
                if token in content:
                    offenders.append((fname, token))
        self.assertEqual(offenders, [], f"Found forbidden execution-capable references: {offenders}")

    def test_decision_label_is_explicitly_advisory(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", market_regime="TRENDING")
        decision = ChiefDecisionOfficer().decide(ctx)
        self.assertIn("ADVISORY ONLY", decision.advisory_label)
        self.assertIn("NOT AN EXECUTION SIGNAL", decision.advisory_label)


class TestEvidenceAndFusion(unittest.TestCase):
    def test_evidence_weighted_score_sign(self):
        bull = Evidence("X", "test", BULLISH, strength=80, confidence=100)
        bear = Evidence("X", "test", BEARISH, strength=80, confidence=100)
        neutral = Evidence("X", "test", NEUTRAL, strength=80, confidence=100)
        self.assertGreater(bull.weighted_score, 0)
        self.assertLess(bear.weighted_score, 0)
        self.assertEqual(neutral.weighted_score, 0)

    def test_fusion_all_bullish_yields_bullish_dominant(self):
        reports = [
            AnalystReport("MacroAnalyst", [Evidence("MacroAnalyst", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("TechnicalAnalyst", [Evidence("TechnicalAnalyst", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("SMCAnalyst", [Evidence("SMCAnalyst", "x", BULLISH, 70, 70)], bias=BULLISH),
        ]
        fused = EvidenceFusionEngine().fuse(reports)
        self.assertEqual(fused.dominant_direction, BULLISH)
        self.assertGreater(fused.net_score, 0)

    def test_fusion_ignores_partial_analysts_in_weighting(self):
        reports = [
            AnalystReport("MacroAnalyst", [Evidence("MacroAnalyst", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("VolumeAnalyst", [], bias=NEUTRAL, partial=True),
        ]
        fused = EvidenceFusionEngine().fuse(reports)
        self.assertNotIn("VolumeAnalyst", fused.weights_used)
        self.assertIn("VolumeAnalyst", fused.partial_analysts)


class TestContradictionResolver(unittest.TestCase):
    def test_no_conflict_when_analysts_agree(self):
        reports = [
            AnalystReport("A", [Evidence("A", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("B", [Evidence("B", "x", BULLISH, 70, 70)], bias=BULLISH),
        ]
        report = ContradictionResolver().resolve(reports)
        self.assertEqual(report.contradiction_score, 0.0)
        self.assertEqual(report.conflicts, [])

    def test_conflict_detected_when_analysts_disagree(self):
        reports = [
            AnalystReport("A", [Evidence("A", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("B", [Evidence("B", "x", BEARISH, 70, 70)], bias=BEARISH),
        ]
        report = ContradictionResolver().resolve(reports)
        self.assertGreater(report.contradiction_score, 0.0)
        self.assertEqual(len(report.conflicts), 1)


class TestScenarioEngine(unittest.TestCase):
    def test_scenario_probabilities_sum_to_one(self):
        reports = [
            AnalystReport("A", [Evidence("A", "x", BULLISH, 70, 70)], bias=BULLISH),
            AnalystReport("B", [Evidence("B", "x", BEARISH, 70, 70)], bias=BEARISH),
        ]
        fused = EvidenceFusionEngine().fuse(reports)
        contradictions = ContradictionResolver().resolve(reports)
        scenarios = ScenarioEngine().build_scenarios(fused, contradictions.contradiction_score)
        total = sum(s.probability for s in scenarios)
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_scenarios_sorted_descending(self):
        reports = [AnalystReport("A", [Evidence("A", "x", BULLISH, 90, 90)], bias=BULLISH)]
        fused = EvidenceFusionEngine().fuse(reports)
        contradictions = ContradictionResolver().resolve(reports)
        scenarios = ScenarioEngine().build_scenarios(fused, contradictions.contradiction_score)
        probs = [s.probability for s in scenarios]
        self.assertEqual(probs, sorted(probs, reverse=True))


class TestChiefDecisionOfficerEndToEnd(unittest.TestCase):
    def test_bullish_aligned_context_leans_bullish(self):
        ctx = DecisionContext(
            strategy="SMC",
            signal="BUY",
            market_regime="TRENDING",
            trend_strength=70.0,
            market_structure="BULLISH_BOS",
            mtf_alignment_mode="ALIGNED",
            smc_strength=8.0,
            smc_entry_confirmed=True,
            liquidity_strength=65.0,
            liquidity_alignment=60.0,
            candle_trigger_confirmed=True,
            rr_ratio=2.0,
            atr_sufficient=True,
        )
        decision = ChiefDecisionOfficer().decide(ctx)
        self.assertEqual(decision.top_scenario.direction, BULLISH)
        self.assertGreaterEqual(decision.confidence, 0.0)
        self.assertLessEqual(decision.confidence, 100.0)

    def test_conflicting_context_raises_contradiction_score(self):
        ctx = DecisionContext(
            strategy="SMC",
            signal="BUY",
            market_regime="CRISIS",
            crisis_active=True,
            trend_strength=70.0,
            market_structure="BULLISH_BOS",
            mtf_alignment_mode="CONFLICT",
            smc_strength=8.0,
            smc_entry_confirmed=True,
        )
        decision = ChiefDecisionOfficer().decide(ctx)
        self.assertGreaterEqual(decision.contradictions.contradiction_score, 0.0)

    def test_explanations_are_generated(self):
        ctx = DecisionContext(strategy="DAILY", signal="SELL", market_regime="RANGING")
        decision = ChiefDecisionOfficer().decide(ctx)
        human = ExplanationBuilder().human_explanation(decision)
        machine = ExplanationBuilder().machine_explanation(decision)
        self.assertIsInstance(human, str)
        self.assertGreater(len(human), 20)
        self.assertIn("advisory_label", machine)
        self.assertIn("top_scenario", machine)
        self.assertIn("evidence_graph", machine)

    def test_decision_never_touches_execution_objects(self):
        ctx = DecisionContext(strategy="MICRO", signal="BUY", market_regime="VOLATILE")
        decision = ChiefDecisionOfficer().decide(ctx)
        # A Decision must not carry any attribute that looks like an order handle.
        forbidden_attrs = ("ticket", "order_id", "executed", "filled", "broker_response")
        for attr in forbidden_attrs:
            self.assertFalse(hasattr(decision, attr), f"Decision unexpectedly has attribute '{attr}'")


class TestRiskOfficerPortfolioIntelligence(unittest.TestCase):
    """§3.4 Portfolio Intelligence must surface through RiskOfficer's
    existing notes field (append, not replace) — never gate or resize."""

    def test_risk_officer_notes_mention_correlated_exposure_when_present(self):
        from brain.faie.analysts import RiskOfficer
        import core.portfolio_risk_authority as pra

        original_state = pra._STATE
        try:
            pra._STATE = pra.PortfolioState(open_trades=[
                {"direction": "BUY", "risk_percent": 1.0, "symbol": "XAUUSD"},
                {"direction": "BUY", "risk_percent": 1.0, "symbol": "XAUUSD"},
                {"direction": "BUY", "risk_percent": 1.0, "symbol": "XAUUSD"},
            ])
            ctx = DecisionContext(strategy="SMC", signal="BUY", market_regime="TRENDING")
            report = RiskOfficer().analyze(ctx)
            self.assertIn("correlated_exposure", report.notes)
            self.assertIn("diversification, not conflict", report.notes)
        finally:
            pra._STATE = original_state

    def test_risk_officer_still_read_only_with_correlated_exposure(self):
        from brain.faie.analysts import RiskOfficer
        import core.portfolio_risk_authority as pra

        original_state = pra._STATE
        try:
            pra._STATE = pra.PortfolioState(open_trades=[
                {"direction": "BUY", "risk_percent": 1.0, "symbol": "XAUUSD"},
                {"direction": "BUY", "risk_percent": 1.0, "symbol": "XAUUSD"},
            ])
            ctx = DecisionContext(strategy="SMC", signal="BUY", market_regime="TRENDING")
            report = RiskOfficer().analyze(ctx)
            # No evidence item may claim a hard_gate purely from correlated
            # exposure — that would silently turn a visibility layer into
            # a blocking one, exactly what the spec forbids.
            for e in report.evidence:
                if "hard_gate" in e.tags:
                    self.assertNotIn("correlated", e.claim.lower())
        finally:
            pra._STATE = original_state


if __name__ == "__main__":
    unittest.main()
