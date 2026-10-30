# =============================================================================
# FER3ON V6 Recovery+ — Unit tests (no MT5 required)
# =============================================================================

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSmcArbitration(unittest.TestCase):
    def test_counter_trend_opportunity(self):
        from brain.smc_arbitration import analyze_smc_arbitration

        r = analyze_smc_arbitration(
            smc_signal="BUY",
            smc_strength=14.0,
            signal="BUY",
            daily_bias="SELL",
            structure_bias="SELL",
            liquidity_bias="SELL",
            mtf_direction="SELL",
            buy_score=14.0,
            sell_score=4.0,
        )
        self.assertEqual(r["classification"], "COUNTER_TREND_OPPORTUNITY")
        self.assertGreater(r["smc_arbitration_score"], 0)
        self.assertGreater(r["confidence_bonus"], 0)

    def test_not_dominant(self):
        from brain.smc_arbitration import analyze_smc_arbitration

        r = analyze_smc_arbitration(
            smc_signal="BUY",
            smc_strength=5.0,
            signal="BUY",
            daily_bias="BUY",
            structure_bias="BUY",
            liquidity_bias="BUY",
            mtf_direction="BUY",
            buy_score=5.0,
            sell_score=4.0,
        )
        self.assertEqual(r["classification"], "CONFLICT")
        self.assertEqual(r["confidence_bonus"], 0.0)


class TestFilterRelaxation(unittest.TestCase):
    def test_no_relax_below_threshold(self):
        from brain.filter_relaxation import compute_filter_relaxation_factor

        self.assertEqual(compute_filter_relaxation_factor(20.0, 60.0), 1.0)

    def test_relax_at_high_false_rate(self):
        from brain.filter_relaxation import compute_filter_relaxation_factor

        factor = compute_filter_relaxation_factor(50.0, 30.0)
        self.assertLess(factor, 1.0)
        self.assertGreaterEqual(factor, 0.8)

    def test_threshold_relaxation(self):
        from brain.filter_relaxation import apply_threshold_relaxation

        relaxed = apply_threshold_relaxation(60.0, 0.9)
        self.assertLess(relaxed, 60.0)


class TestHardRiskCap(unittest.TestCase):
    def test_cap_per_trade(self):
        from risk.hard_risk_cap import cap_risk_percent

        capped = cap_risk_percent(0.75)
        self.assertLessEqual(capped, 0.50)

    def test_emergency_stop_on_daily_loss(self):
        from risk import hard_risk_cap

        hard_risk_cap._daily_loss_amount = 0.0
        hard_risk_cap._emergency_stop = False
        hard_risk_cap._last_reset_day = None

        r = hard_risk_cap.check_hard_risk_cap(
            account_balance=10000.0,
            requested_risk_percent=0.3,
            daily_loss_amount=1001.0,
        )
        self.assertEqual(r["hard_risk_status"], "EMERGENCY_STOP")
        self.assertFalse(r["allowed"])

    def test_daily_loss_limit_is_fixed_dollars(self):
        from risk import hard_risk_cap

        hard_risk_cap._daily_loss_amount = 0.0
        hard_risk_cap._emergency_stop = False
        hard_risk_cap._last_reset_day = None
        result = hard_risk_cap.check_hard_risk_cap(
            account_balance=5000.0,
            requested_risk_percent=0.3,
            daily_loss_amount=100.01,
        )
        self.assertEqual(result["daily_loss_limit"], 100.0)
        self.assertFalse(result["allowed"])


class TestSessionIntelligence(unittest.TestCase):
    def test_detect_overlap(self):
        from core.session_intelligence import detect_session_phase

        self.assertEqual(detect_session_phase(14), "OVERLAP")

    def test_london_sweep_phase(self):
        from core.session_intelligence import detect_session_phase

        self.assertEqual(detect_session_phase(9), "LONDON_SWEEP")

    def test_analyze_returns_modifiers(self):
        from core.session_intelligence import analyze_session_intelligence

        r = analyze_session_intelligence(14, signal="BUY")
        self.assertIn("session_intelligence_score", r)
        self.assertIn("confidence_modifier", r)
        self.assertIn("risk_modifier", r)


class TestRecoveryDashboard(unittest.TestCase):
    def test_compute_metrics_empty(self):
        from analytics.recovery_dashboard import compute_recovery_metrics

        m = compute_recovery_metrics(
            missed_opportunity_stats={"false_rejection_rate": 25, "missed_opportunity_score": 75},
            trades=[],
        )
        self.assertEqual(m["total_trades"], 0)
        self.assertEqual(m["false_rejection_rate"], 25)

    def test_win_rate_calculation(self):
        from analytics.recovery_dashboard import compute_recovery_metrics

        trades = [
            {"result": "WIN", "profit": 10, "confidence": 70, "opportunistic": True},
            {"result": "LOSS", "profit": -5, "confidence": 65, "opportunistic": True},
        ]
        m = compute_recovery_metrics(trades=trades)
        self.assertEqual(m["opportunity_engine_win_rate"], 50.0)


class TestBrainUnifiedPenaltyReduction(unittest.TestCase):
    def test_conflict_penalty_reduced(self):
        from core.brain_unified import compute_final_brain_score

        base = compute_final_brain_score(
            master_score=50,
            confidence_pct=60,
            quality_score=55,
            exec_grade="B",
            conflict_report={
                "aligned_count": 1,
                "opposed_count": 4,
            },
            conflict_penalty_reduction=0.0,
        )
        reduced = compute_final_brain_score(
            master_score=50,
            confidence_pct=60,
            quality_score=55,
            exec_grade="B",
            conflict_report={
                "aligned_count": 1,
                "opposed_count": 4,
            },
            conflict_penalty_reduction=6.0,
        )
        self.assertGreater(reduced["final_score"], base["final_score"])


if __name__ == "__main__":
    unittest.main()
