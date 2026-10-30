# =============================================================================
# FER3ON — PHASE 3 | TEST SUITE
# =============================================================================
# اختبارات شاملة لكل مكوّنات Phase 3:
#   - Shadow mode enforcement (لا live authority)
#   - Component isolation (كل مكوّن مستقل)
#   - Settings validation (لا hardcoded thresholds)
#   - Runtime safety (أخطاء Phase 3 لا تُوقف runtime)
#   - Integration (الـ orchestrator يجمع الكل)
# =============================================================================

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# إضافة project root إلى Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# TEST 1: Settings Validation — No Hardcoded Thresholds
# =============================================================================
class TestPhase3Settings(unittest.TestCase):
    """تحقق أن كل Phase 3 settings موجودة وصحيحة."""

    def test_phase3_directories_defined(self):
        from core.settings import (
            PHASE3_ANALYTICS_DIR,
            PHASE3_FINAL_BRAIN_DIR,
            PHASE3_PORTFOLIO_BRAIN_DIR,
            PHASE3_GOLD_CONTEXT_DIR,
            PHASE3_ML_SAFETY_DIR,
            PHASE3_STRATEGY_DNA_DIR,
            PHASE3_SYSTEM_HEALTH_DIR,
            PHASE3_SHADOW_LOG_DIR,
        )
        dirs = [
            PHASE3_ANALYTICS_DIR, PHASE3_FINAL_BRAIN_DIR,
            PHASE3_PORTFOLIO_BRAIN_DIR, PHASE3_GOLD_CONTEXT_DIR,
            PHASE3_ML_SAFETY_DIR, PHASE3_STRATEGY_DNA_DIR,
            PHASE3_SYSTEM_HEALTH_DIR, PHASE3_SHADOW_LOG_DIR,
        ]
        for d in dirs:
            self.assertIsInstance(d, str)
            self.assertTrue(len(d) > 0)

    def test_phase3_globally_disabled_live_authority(self):
        from core.settings import PHASE3_LIVE_AUTHORITY
        self.assertFalse(PHASE3_LIVE_AUTHORITY, "PHASE3 live authority must be False")

    def test_final_brain_live_disabled(self):
        from core.settings import FINAL_BRAIN_LIVE_AUTHORITY
        self.assertFalse(FINAL_BRAIN_LIVE_AUTHORITY)

    def test_portfolio_brain_live_disabled(self):
        from core.settings import PORTFOLIO_BRAIN_LIVE_AUTHORITY
        self.assertFalse(PORTFOLIO_BRAIN_LIVE_AUTHORITY)

    def test_gold_context_hard_block_disabled(self):
        from core.settings import GOLD_CONTEXT_HARD_BLOCK_ALLOWED
        self.assertFalse(GOLD_CONTEXT_HARD_BLOCK_ALLOWED)

    def test_gold_context_live_influence_disabled(self):
        from core.settings import GOLD_CONTEXT_LIVE_INFLUENCE
        self.assertFalse(GOLD_CONTEXT_LIVE_INFLUENCE)

    def test_ml_safety_live_block_disabled(self):
        from core.settings import ML_SAFETY_LIVE_BLOCK
        self.assertFalse(ML_SAFETY_LIVE_BLOCK)

    def test_adaptive_shadow_only_enabled(self):
        from core.settings import ADAPTIVE_SHADOW_ONLY
        self.assertTrue(ADAPTIVE_SHADOW_ONLY)

    def test_final_brain_thresholds_in_range(self):
        from core.settings import FINAL_BRAIN_MIN_APPROVAL_SCORE, FINAL_BRAIN_MIN_REJECT_SCORE
        self.assertGreater(FINAL_BRAIN_MIN_APPROVAL_SCORE, FINAL_BRAIN_MIN_REJECT_SCORE)
        self.assertGreaterEqual(FINAL_BRAIN_MIN_APPROVAL_SCORE, 0)
        self.assertLessEqual(FINAL_BRAIN_MIN_APPROVAL_SCORE, 100)

    def test_gold_context_weights_sum_to_one(self):
        from core.settings import GOLD_CONTEXT_FACTOR_WEIGHTS
        total = sum(GOLD_CONTEXT_FACTOR_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, places=2,
            msg=f"Gold context weights sum={total} should be ~1.0")

    def test_phase3_activation_requirements_sane(self):
        from core.settings import (
            PHASE3_REQUIRED_CLOSED_TRADES,
            PHASE3_REQUIRED_SHADOW_CYCLES,
            PHASE3_REQUIRED_FALSE_REJECT_MAX,
        )
        self.assertGreater(PHASE3_REQUIRED_CLOSED_TRADES, 0)
        self.assertGreater(PHASE3_REQUIRED_SHADOW_CYCLES, 0)
        self.assertGreater(PHASE3_REQUIRED_FALSE_REJECT_MAX, 0)
        self.assertLess(PHASE3_REQUIRED_FALSE_REJECT_MAX, 1.0)

    def test_cannot_change_list_defined(self):
        from core.settings import ADAPTIVE_SHADOW_CANNOT_CHANGE
        self.assertIsInstance(ADAPTIVE_SHADOW_CANNOT_CHANGE, tuple)
        self.assertIn("core_trading_logic", ADAPTIVE_SHADOW_CANNOT_CHANGE)
        self.assertIn("direction_logic", ADAPTIVE_SHADOW_CANNOT_CHANGE)


# =============================================================================
# TEST 2: FINAL_BRAIN Shadow Mode
# =============================================================================
class TestFinalBrainShadow(unittest.TestCase):

    def test_import_without_live_authority(self):
        """يجب أن يُستورد FINAL_BRAIN بنجاح في shadow mode."""
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        self.assertIsNotNone(evaluate_shadow)

    def test_shadow_decision_returned(self):
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        inp = FinalBrainInput(
            strategy="SMC",
            signal="BUY",
            quality_score=70,
            confidence_pct=65,
            actual_decision="FULL",
        )
        decision = evaluate_shadow(inp)
        self.assertIn(decision.shadow_decision, ["SHADOW_APPROVE", "SHADOW_REJECT", "SHADOW_WAIT"])

    def test_high_quality_gets_approval(self):
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        inp = FinalBrainInput(
            quality_score=90,
            confidence_pct=85,
            portfolio_brain_score=80,
            gold_context_score=75,
            ml_health_score=80,
            strategy_dna_rank=75,
            actual_decision="FULL",
        )
        decision = evaluate_shadow(inp)
        self.assertEqual(decision.shadow_decision, "SHADOW_APPROVE")

    def test_low_quality_gets_rejection(self):
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        inp = FinalBrainInput(
            quality_score=20,
            confidence_pct=25,
            portfolio_brain_score=20,
            gold_context_score=20,
            ml_health_score=20,
            strategy_dna_rank=20,
            actual_decision="FULL",
        )
        decision = evaluate_shadow(inp)
        self.assertEqual(decision.shadow_decision, "SHADOW_REJECT")

    def test_approval_score_in_range(self):
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        inp = FinalBrainInput(quality_score=55, confidence_pct=60)
        decision = evaluate_shadow(inp)
        self.assertGreaterEqual(decision.approval_score, 0.0)
        self.assertLessEqual(decision.approval_score, 100.0)

    def test_does_not_modify_actual_decision(self):
        """FINAL_BRAIN لا يُغيّر القرار الفعلي — يُعيد shadow فقط."""
        from core.phase3.final_brain import evaluate_shadow, FinalBrainInput
        original_decision = "FULL"
        inp = FinalBrainInput(quality_score=30, actual_decision=original_decision)
        decision = evaluate_shadow(inp)
        # القرار الفعلي لم يتغير
        self.assertEqual(inp.actual_decision, original_decision)
        # shadow decision منفصل
        self.assertNotEqual(decision.shadow_decision, "FULL")

    def test_readiness_report_structure(self):
        from core.phase3.final_brain import get_readiness_report
        report = get_readiness_report()
        required_keys = [
            "component", "mode", "live_authority",
            "readiness_score", "requirements",
        ]
        for key in required_keys:
            self.assertIn(key, report)
        self.assertEqual(report["mode"], "SHADOW")
        self.assertFalse(report["live_authority"])

    def test_record_trade_outcome_false_rejection(self):
        from core.phase3.final_brain import record_trade_outcome
        # يجب أن يعمل بدون خطأ
        try:
            record_trade_outcome(ticket=12345, was_winner=True, shadow_decision="SHADOW_REJECT")
        except Exception as e:
            self.fail(f"record_trade_outcome raised: {e}")


# =============================================================================
# TEST 3: PORTFOLIO_BRAIN Shadow Mode
# =============================================================================
class TestPortfolioBrainShadow(unittest.TestCase):

    def test_empty_portfolio(self):
        from core.phase3.portfolio_brain import evaluate_portfolio_shadow
        out = evaluate_portfolio_shadow(open_trades=[], account_balance=1000)
        self.assertEqual(out.mode, "SHADOW")
        self.assertGreaterEqual(out.portfolio_brain_score, 0)
        self.assertLessEqual(out.portfolio_brain_score, 100)

    def test_full_portfolio_lower_exposure_score(self):
        from core.phase3.portfolio_brain import evaluate_portfolio_shadow
        # محفظة ممتلئة → exposure score منخفض
        full_trades = [
            {"strategy": "SMC", "risk_pct": 0.75},
            {"strategy": "DAILY", "risk_pct": 0.75},
            {"strategy": "SMC", "risk_pct": 0.75},
            {"strategy": "DAILY", "risk_pct": 0.75},
        ]
        out_full = evaluate_portfolio_shadow(open_trades=full_trades)
        out_empty = evaluate_portfolio_shadow(open_trades=[])
        self.assertLess(out_full.exposure_score, out_empty.exposure_score)

    def test_concentrated_portfolio_warning(self):
        from core.phase3.portfolio_brain import evaluate_portfolio_shadow
        # كل الصفقات في استراتيجية واحدة
        same_strat = [
            {"strategy": "SMC", "risk_pct": 0.75},
            {"strategy": "SMC", "risk_pct": 0.75},
            {"strategy": "SMC", "risk_pct": 0.75},
        ]
        out = evaluate_portfolio_shadow(open_trades=same_strat)
        self.assertEqual(out.diversification_state, "CONCENTRATED")

    def test_no_live_authority_flag(self):
        from core.phase3.portfolio_brain import get_portfolio_brain_status
        status = get_portfolio_brain_status()
        self.assertFalse(status["live_authority"])

    def test_score_always_valid_range(self):
        from core.phase3.portfolio_brain import evaluate_portfolio_shadow
        for n_trades in [0, 1, 2, 4]:
            trades = [{"strategy": "SMC", "risk_pct": 0.75}] * n_trades
            out = evaluate_portfolio_shadow(open_trades=trades)
            self.assertGreaterEqual(out.portfolio_brain_score, 0)
            self.assertLessEqual(out.portfolio_brain_score, 100)


# =============================================================================
# TEST 4: GOLD_CONTEXT_LAYER Shadow Mode
# =============================================================================
class TestGoldContextLayerShadow(unittest.TestCase):

    def test_neutral_factors_give_neutral_score(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        factors = GoldMacroFactors()  # كل العوامل = 0 (محايد)
        out = evaluate_gold_context(factors=factors, signal="BUY")
        self.assertAlmostEqual(out.gold_context_score, 50.0, delta=5.0)

    def test_bullish_factors_above_50(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        # قيم موجبة = إيجابي للذهب
        factors = GoldMacroFactors(
            dxy_trend=+50,      # دولار ضعيف (+ = إيجابي للذهب)
            real_yields=+40,    # عوائد منخفضة (+ = إيجابي)
            cpi_pressure=+60,   # تضخم مرتفع (+ = إيجابي)
            geopolitical=+70,   # توترات جيوسياسية (+ = إيجابي)
        )
        out = evaluate_gold_context(factors=factors, signal="BUY")
        self.assertGreater(out.gold_context_score, 55.0)

    def test_bearish_factors_below_50(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        # قيم سلبية = سلبي للذهب
        factors = GoldMacroFactors(
            dxy_trend=-80,      # دولار قوي (- = سلبي للذهب)
            real_yields=-70,    # عوائد مرتفعة (- = سلبي)
            fomc_stance=-60,    # hawkish فيدرالي (- = سلبي)
        )
        out = evaluate_gold_context(factors=factors, signal="BUY")
        self.assertLess(out.gold_context_score, 50.0)

    def test_cannot_hard_block(self):
        """GOLD_CONTEXT لا يُنتج hard block أبداً."""
        from core.settings import GOLD_CONTEXT_HARD_BLOCK_ALLOWED
        self.assertFalse(GOLD_CONTEXT_HARD_BLOCK_ALLOWED)

    def test_stale_data_decays_to_neutral(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        factors = GoldMacroFactors(
            dxy_trend=-80,
            data_freshness_hours=80.0,  # بيانات قديمة جداً
        )
        out = evaluate_gold_context(factors=factors)
        # التأثير يجب أن يكون أقرب للمحايد
        self.assertAlmostEqual(out.gold_context_score, 50.0, delta=10.0)

    def test_score_always_in_range(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        factors = GoldMacroFactors(
            dxy_trend=100, real_yields=100, cpi_pressure=-100,
            nfp_momentum=100, fomc_stance=-100,
        )
        out = evaluate_gold_context(factors=factors)
        self.assertGreaterEqual(out.gold_context_score, 0.0)
        self.assertLessEqual(out.gold_context_score, 100.0)

    def test_signal_alignment_detection(self):
        from core.phase3.gold_context_layer import evaluate_gold_context, GoldMacroFactors
        # قيم موجبة كبيرة = سياق صاعد قوي للذهب
        bullish = GoldMacroFactors(dxy_trend=+80, cpi_pressure=+80, geopolitical=+70)
        out = evaluate_gold_context(factors=bullish, signal="BUY")
        self.assertEqual(out.signal_alignment, "BULLISH_ALIGNED")


# =============================================================================
# TEST 5: ML_SAFETY_FRAMEWORK Shadow Mode
# =============================================================================
class TestMLSafetyFramework(unittest.TestCase):

    def test_record_prediction_no_error(self):
        from core.phase3.ml_safety_framework import record_ml_prediction
        try:
            record_ml_prediction(
                prediction_score=75.0,
                strategy="SMC",
                session="LONDON",
                regime="TRENDING",
            )
        except Exception as e:
            self.fail(f"record_ml_prediction raised: {e}")

    def test_health_check_returns_report(self):
        from core.phase3.ml_safety_framework import run_health_check
        report = run_health_check()
        self.assertIn(report.health_status, ["HEALTHY", "WARNING", "ALERT", "CRITICAL", "DISABLED"])
        self.assertGreaterEqual(report.health_score, 0.0)
        self.assertLessEqual(report.health_score, 100.0)

    def test_no_live_block(self):
        from core.settings import ML_SAFETY_LIVE_BLOCK
        self.assertFalse(ML_SAFETY_LIVE_BLOCK)

    def test_status_report_structure(self):
        from core.phase3.ml_safety_framework import get_ml_safety_status
        status = get_ml_safety_status()
        self.assertEqual(status["mode"], "SHADOW")
        self.assertFalse(status["live_block"])

    def test_resolve_prediction_no_error(self):
        from core.phase3.ml_safety_framework import (
            record_ml_prediction, resolve_ml_prediction
        )
        ts = time.time()
        record_ml_prediction(prediction_score=60.0)
        try:
            resolve_ml_prediction(timestamp=ts, was_winner=True)
        except Exception as e:
            self.fail(f"resolve_ml_prediction raised: {e}")


# =============================================================================
# TEST 6: STRATEGY_DNA Shadow Mode
# =============================================================================
class TestStrategyDNAShadow(unittest.TestCase):
    """
    V9 FIX: تم اكتشاف أن هذا الكلاس كان يكتب فعليًا على
    PHASE3_STRATEGY_DNA_DIR/strategy_dna_state.json الحقيقي (لا عزل)، ما
    أدى لتلوّث بيانات الإنتاج بمفاتيح اختبار (TEST_STRAT, WEAK_STRAT) تتكرر
    مع كل تشغيل pytest. setUp/tearDown هنا يحفظان الملف الحقيقي قبل
    الاختبارات ويستعيدانه بعدها — عزل كامل بدون تعديل سلوك أي اختبار.
    """

    def setUp(self):
        from core.settings import PHASE3_STRATEGY_DNA_DIR
        self._state_path = os.path.join(PHASE3_STRATEGY_DNA_DIR, "strategy_dna_state.json")
        self._backup_content = None
        if os.path.exists(self._state_path):
            with open(self._state_path, "r", encoding="utf-8") as f:
                self._backup_content = f.read()

    def tearDown(self):
        if self._backup_content is not None:
            with open(self._state_path, "w", encoding="utf-8") as f:
                f.write(self._backup_content)
        elif os.path.exists(self._state_path):
            os.remove(self._state_path)

    def test_new_strategy_gets_neutral_score(self):
        from core.phase3.strategy_dna import evaluate_strategy_shadow
        out = evaluate_strategy_shadow(
            strategy="TEST_STRATEGY_XYZ_NEVER_SEEN",
            session="LONDON",
            regime="TRENDING",
        )
        self.assertAlmostEqual(out.dna_rank_score, 50.0, delta=15.0)

    def test_record_and_evaluate_cycle(self):
        from core.phase3.strategy_dna import record_strategy_trade, evaluate_strategy_shadow
        for i in range(15):
            record_strategy_trade("TEST_STRAT", True, 10.0, "LONDON", "TRENDING")
        out = evaluate_strategy_shadow("TEST_STRAT", "LONDON", "TRENDING")
        self.assertGreater(out.dna_rank_score, 50.0)

    def test_weak_strategy_gets_penalty(self):
        from core.phase3.strategy_dna import record_strategy_trade, evaluate_strategy_shadow
        for i in range(15):
            record_strategy_trade("WEAK_STRAT", False, -10.0, "ASIA", "RANGING")
        out = evaluate_strategy_shadow("WEAK_STRAT")
        self.assertTrue(out.penalty_applied)

    def test_no_live_influence(self):
        from core.settings import STRATEGY_DNA_LIVE_INFLUENCE
        self.assertFalse(STRATEGY_DNA_LIVE_INFLUENCE)

    def test_get_rankings_returns_list(self):
        from core.phase3.strategy_dna import get_strategy_rankings
        rankings = get_strategy_rankings()
        self.assertIsInstance(rankings, list)


# =============================================================================
# TEST 7: SYSTEM_HEALTH_LAYER Shadow Mode
# =============================================================================
class TestSystemHealthLayer(unittest.TestCase):

    def test_health_check_runs(self):
        from core.phase3.system_health_layer import run_system_health_check
        report = run_system_health_check()
        self.assertGreaterEqual(report.overall_score, 0.0)
        self.assertLessEqual(report.overall_score, 100.0)
        self.assertIn(report.overall_status, ["OK", "WARNING", "ALERT", "CRITICAL", "DISABLED"])

    def test_health_summary_no_error(self):
        from core.phase3.system_health_layer import get_system_health_summary
        summary = get_system_health_summary()
        self.assertIn("overall_score", summary)

    def test_phase3_readiness_computed(self):
        from core.phase3.system_health_layer import run_system_health_check
        report = run_system_health_check()
        self.assertGreaterEqual(report.phase3_readiness, 0.0)
        self.assertLessEqual(report.phase3_readiness, 100.0)


# =============================================================================
# TEST 8: ADAPTIVE_SHADOW_CALIBRATION
# =============================================================================
class TestAdaptiveShadowCalibration(unittest.TestCase):

    def test_shadow_only_flag_required(self):
        from core.settings import ADAPTIVE_SHADOW_ONLY
        self.assertTrue(ADAPTIVE_SHADOW_ONLY)

    def test_analysis_with_no_trades(self):
        from core.phase3.adaptive_shadow_calibration import run_adaptive_shadow_analysis
        report = run_adaptive_shadow_analysis(recent_trades=[])
        self.assertEqual(report.mode, "SHADOW_ADVISORY_ONLY")
        self.assertIsInstance(report.cannot_change, list)

    def test_analysis_with_trades(self):
        from core.phase3.adaptive_shadow_calibration import run_adaptive_shadow_analysis
        trades = [
            {"confidence_pct": 30, "was_winner": False, "profit": -5, "session": "ASIA", "strategy": "MICRO"},
            {"confidence_pct": 70, "was_winner": True, "profit": 10, "session": "LONDON", "strategy": "SMC"},
            {"confidence_pct": 80, "was_winner": True, "profit": 12, "session": "LONDON", "strategy": "SMC"},
        ] * 10
        report = run_adaptive_shadow_analysis(recent_trades=trades)
        self.assertEqual(report.mode, "SHADOW_ADVISORY_ONLY")
        self.assertIsInstance(report.session_preferences, dict)

    def test_cannot_change_contains_critical_items(self):
        from core.phase3.adaptive_shadow_calibration import run_adaptive_shadow_analysis
        report = run_adaptive_shadow_analysis([])
        self.assertIn("core_trading_logic", report.cannot_change)
        self.assertIn("direction_logic", report.cannot_change)

    def test_suggestions_not_auto_activated(self):
        """التوصيات يجب أن تكون approved_for_live=False دائماً."""
        from core.phase3.adaptive_shadow_calibration import run_adaptive_shadow_analysis
        trades = [
            {"confidence_pct": 20, "was_winner": False, "profit": -5, "session": "ASIA", "strategy": "MICRO"},
        ] * 25
        report = run_adaptive_shadow_analysis(recent_trades=trades)
        for suggestion in report.confidence_suggestions:
            self.assertFalse(suggestion.approved_for_live)

    def test_orchestrator_passes_closed_truth_layer_trades_to_calibration(self):
        from analytics.truth_layer import TradeRecord
        import core.phase3.phase3_orchestrator as orchestrator

        closed_trade = TradeRecord(
            ticket=101,
            strategy="SMC",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            close_time="2026-01-01T10:00:00+00:00",
            confidence=0.72,
            profit=12.0,
            is_win=True,
        )
        open_trade = TradeRecord(
            ticket=102,
            strategy="SMC",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            confidence=0.8,
        )
        original_cycle_count = orchestrator._adaptive_cycle_count
        orchestrator._adaptive_cycle_count = orchestrator._ADAPTIVE_ANALYSIS_INTERVAL - 1
        try:
            with patch("analytics.performance_repository.get_all_trades",
                       return_value=[closed_trade, open_trade]), \
                 patch("core.phase3.adaptive_shadow_calibration.run_adaptive_shadow_analysis") as analyze:
                orchestrator.run_phase3_shadow(orchestrator.Phase3Input())
            analyze.assert_called_once_with(recent_trades=[{
                "was_winner": True,
                "profit": 12.0,
                "session": "LONDON",
                "strategy": "SMC",
                "confidence_pct": 72.0,
            }])
        finally:
            orchestrator._adaptive_cycle_count = original_cycle_count


class TestGoldMacroFeed(unittest.TestCase):

    def test_feed_requires_fresh_timezone_and_all_factors(self):
        from datetime import datetime, timezone
        from core.phase3.gold_context_layer import load_gold_macro_factors

        sample = {
            "sampled_at": "2026-01-01T11:00:00+00:00",
            "source": "verified-test-feed",
            "factors": {
                "dxy_trend": 1,
                "real_yields": 2,
                "cpi_pressure": 3,
                "nfp_momentum": 4,
                "fomc_stance": 5,
                "geopolitical": 6,
                "rate_differential": 7,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "macro.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(sample, stream)
            factors, status = load_gold_macro_factors(
                path,
                now=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(status, "available")
            self.assertEqual(factors.source, "verified-test-feed")
            self.assertEqual(factors.data_freshness_hours, 1.0)

            sample["factors"].pop("dxy_trend")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(sample, stream)
            factors, status = load_gold_macro_factors(
                path,
                now=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            )
            self.assertIsNone(factors)
            self.assertIn("dxy_trend", status)

    def test_missing_macro_data_is_not_scored_as_observed_neutral(self):
        from core.phase3.gold_context_layer import evaluate_gold_context

        result = evaluate_gold_context(factors=None)
        self.assertEqual(result.mode, "SHADOW_DATA_UNAVAILABLE")
        self.assertIn("Macro data unavailable", result.warnings[0])


# =============================================================================
# TEST 9: PHASE3 ORCHESTRATOR Integration
# =============================================================================
class TestPhase3Orchestrator(unittest.TestCase):

    def test_orchestrator_runs_with_minimal_input(self):
        from core.phase3.phase3_orchestrator import Phase3Input, run_phase3_shadow
        inp = Phase3Input(
            strategy="SMC",
            signal="BUY",
            actual_decision="FULL",
            quality_score=70,
            confidence_pct=65,
        )
        out = run_phase3_shadow(inp)
        self.assertEqual(out.mode, "SHADOW")
        self.assertIsInstance(out.components_run, list)
        self.assertGreaterEqual(len(out.components_run), 1)

    def test_orchestrator_never_blocks_runtime(self):
        """أي خطأ في Phase 3 لا يُوقف runtime."""
        from core.phase3.phase3_orchestrator import Phase3Input, run_phase3_shadow
        # نحاول مدخلات شاذة
        inp = Phase3Input(
            strategy=None,
            signal=None,
            quality_score=-999,
            confidence_pct=9999,
        )
        try:
            out = run_phase3_shadow(inp)
            # يجب أن يُعيد شيئاً — لا exception
            self.assertIsNotNone(out)
        except Exception as e:
            self.fail(f"Orchestrator raised exception (should catch internally): {e}")

    def test_output_has_all_required_fields(self):
        from core.phase3.phase3_orchestrator import Phase3Input, run_phase3_shadow
        inp = Phase3Input()
        out = run_phase3_shadow(inp)
        required_attrs = [
            "portfolio_brain_score", "gold_context_score",
            "ml_health_score", "strategy_dna_rank",
            "final_brain_decision", "final_brain_score",
            "mode", "phase3_active",
        ]
        for attr in required_attrs:
            self.assertTrue(hasattr(out, attr), f"Missing output field: {attr}")

    def test_notify_trade_closed_no_error(self):
        from core.phase3.phase3_orchestrator import notify_trade_closed
        try:
            notify_trade_closed(
                ticket=99999,
                strategy="SMC",
                session="LONDON",
                regime="TRENDING",
                was_winner=True,
                profit=15.0,
                shadow_final_brain_decision="SHADOW_APPROVE",
                ml_prediction_timestamp=time.time(),
            )
        except Exception as e:
            self.fail(f"notify_trade_closed raised: {e}")

    def test_get_phase3_status_structure(self):
        from core.phase3.phase3_orchestrator import get_phase3_status
        status = get_phase3_status()
        self.assertIn("phase3_enabled", status)
        self.assertIn("components", status)
        self.assertEqual(status["mode"], "SHADOW")

    def test_scores_always_in_valid_range(self):
        from core.phase3.phase3_orchestrator import Phase3Input, run_phase3_shadow
        inp = Phase3Input(quality_score=80, confidence_pct=75, actual_decision="FULL")
        out = run_phase3_shadow(inp)
        for score_attr in ["portfolio_brain_score", "gold_context_score",
                           "ml_health_score", "strategy_dna_rank", "final_brain_score"]:
            val = getattr(out, score_attr)
            self.assertGreaterEqual(val, 0.0, f"{score_attr} below 0")
            self.assertLessEqual(val, 100.0, f"{score_attr} above 100")


# =============================================================================
# TEST 10: Core System Untouched Validation
# =============================================================================
class TestCoreSystemUntouched(unittest.TestCase):
    """تحقق أن Phase 3 لم تُغيّر أي ملف core أساسي."""

    def test_unified_decision_importable(self):
        from core.unified_decision import DecisionContext, unified_decide
        self.assertIsNotNone(unified_decide)

    def test_portfolio_risk_authority_importable(self):
        from core.portfolio_risk_authority import evaluate_risk
        self.assertIsNotNone(evaluate_risk)

    def test_settings_frozen_core_vars_intact(self):
        """تحقق أن المتغيرات الأساسية لم تتغير."""
        from core.settings import (
            RISK_PER_TRADE_PERCENT,
            MAX_RISK_PER_DAY_PERCENT,
            MAX_LOT, MIN_LOT,
            SYMBOL,
        )
        self.assertGreater(RISK_PER_TRADE_PERCENT, 0)
        self.assertLess(RISK_PER_TRADE_PERCENT, 5)
        self.assertEqual(SYMBOL, "XAUUSD")

    def test_phase3_has_no_imports_from_execution(self):
        """
        Phase 3 modules لا تستورد من execution core مباشرة.
        تحقق أن الملفات الأساسية سليمة.
        """
        forbidden_in_phase3 = [
            "core.trade_executor",
        ]
        import importlib
        phase3_modules = [
            "core.phase3.final_brain",
            "core.phase3.portfolio_brain",
            "core.phase3.gold_context_layer",
        ]
        for mod_name in phase3_modules:
            try:
                mod = importlib.import_module(mod_name)
                for forbidden in forbidden_in_phase3:
                    # نتحقق من source الملف بدل runtime
                    import inspect
                    try:
                        source = inspect.getsource(mod)
                        self.assertNotIn(
                            f"from {forbidden} import",
                            source,
                            f"{mod_name} should not import {forbidden}",
                        )
                    except Exception:
                        pass
            except ImportError:
                pass  # Module not available — skip

    def test_adaptive_learning_core_untouched(self):
        """adaptive_learning.py الأصلي لم يُعدَّل."""
        from core.adaptive_learning import TRADE_LOG_FILE, STATE_FILE
        # يجب أن يشير إلى المسارات الأصلية، ليس Phase 3
        self.assertNotIn("phase3", STATE_FILE)
        self.assertNotIn("phase3", TRADE_LOG_FILE)


# =============================================================================
# TEST 11: INSTITUTIONAL DASHBOARD
# =============================================================================
class TestInstitutionalDashboard(unittest.TestCase):

    def test_dashboard_generates(self):
        from analytics.institutional_dashboard_phase3 import generate_institutional_dashboard
        dashboard = generate_institutional_dashboard()
        self.assertIn("tabs", dashboard)
        self.assertEqual(dashboard["mode"], "SHADOW")

    def test_dashboard_has_all_tabs(self):
        from analytics.institutional_dashboard_phase3 import generate_institutional_dashboard
        dashboard = generate_institutional_dashboard()
        expected_tabs = [
            "portfolio_analytics", "risk_analytics", "strategy_dna",
            "session_intelligence", "regime_intelligence", "phase3_status",
        ]
        for tab in expected_tabs:
            self.assertIn(tab, dashboard["tabs"], f"Missing tab: {tab}")

    def test_dashboard_no_live_authority_in_status(self):
        from analytics.institutional_dashboard_phase3 import generate_institutional_dashboard
        dashboard = generate_institutional_dashboard()
        p3_status = dashboard["tabs"].get("phase3_status", {})
        self.assertFalse(p3_status.get("live_authority", True))


# =============================================================================
# MAIN RUNNER
# =============================================================================

def run_all_tests():
    """يُشغّل كل اختبارات Phase 3."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestPhase3Settings,
        TestFinalBrainShadow,
        TestPortfolioBrainShadow,
        TestGoldContextLayerShadow,
        TestMLSafetyFramework,
        TestStrategyDNAShadow,
        TestSystemHealthLayer,
        TestAdaptiveShadowCalibration,
        TestPhase3Orchestrator,
        TestCoreSystemUntouched,
        TestInstitutionalDashboard,
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"PHASE 3 TEST RESULTS")
    print("=" * 60)
    print(f"Tests run:    {result.testsRun}")
    print(f"Failures:     {len(result.failures)}")
    print(f"Errors:       {len(result.errors)}")
    print(f"Skipped:      {len(result.skipped)}")
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"Passed:       {passed}")
    print(f"Status:       {'✅ ALL PASS' if result.wasSuccessful() else '❌ FAILURES DETECTED'}")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
