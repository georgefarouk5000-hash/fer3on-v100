# =============================================================================
# FER3ON V6.0 PRO — SMOKE TEST
# Run this after any change to verify imports and structure are intact
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = []
FAIL = []


def run_check(label, fn):
    try:
        fn()
        PASS.append(label)
        print(f"  ✅ {label}")
    except Exception as e:
        FAIL.append((label, str(e)))
        print(f"  ❌ {label}: {e}")


def main() -> int:
    print("\n🔬 FER3ON V6.0 PRO — SMOKE TEST\n")

    print("[ SETTINGS ]")
    run_check("settings", lambda: __import__("core.settings", fromlist=["BOT_NAME"]))

    print("\n[ CORE ENGINES ]")
    run_check("atr_manager", lambda: __import__("core.atr_manager", fromlist=["calculate_atr"]))
    run_check("market_regime", lambda: __import__("core.market_regime", fromlist=["detect_market_regime"]))
    run_check("session_intelligence", lambda: __import__("core.session_intelligence", fromlist=["get_session"]))
    run_check("news_filter", lambda: __import__("core.news_filter", fromlist=["is_news_time"]))
    run_check("quality_score", lambda: __import__("core.quality_score", fromlist=["calculate_quality_score"]))
    run_check("risk_manager", lambda: __import__("core.risk_manager", fromlist=["calculate_smart_lot"]))
    run_check("crisis_intelligence", lambda: __import__("core.crisis_intelligence", fromlist=["get_crisis_state"]))
    run_check("candle_patterns", lambda: __import__("core.candle_patterns", fromlist=["detect_hammer"]))
    run_check("candle_engine", lambda: __import__("core.candle_engine", fromlist=["score_candle_strength"]))
    run_check("candle_trigger", lambda: __import__("core.candle_trigger", fromlist=["check_candle_trigger"]))
    run_check("smc_entry_engine", lambda: __import__("core.smc_entry_engine", fromlist=["check_smc_entry_sequence"]))
    run_check("confidence_engine", lambda: __import__("core.confidence_engine", fromlist=["get_confidence_v51"]))
    run_check("liquidity_intelligence", lambda: __import__("core.liquidity_intelligence", fromlist=["get_liquidity_bias"]))
    run_check("liquidity_map", lambda: __import__("core.liquidity_map", fromlist=["build_liquidity_map"]))
    run_check("market_structure", lambda: __import__("core.market_structure", fromlist=["get_market_structure_v51"]))
    run_check("choch_engine", lambda: __import__("core.choch_engine", fromlist=["get_full_structure_analysis"]))
    run_check("execution_quality", lambda: __import__("core.execution_quality", fromlist=["evaluate_execution_quality"]))
    run_check("execution_intelligence", lambda: __import__("core.execution_intelligence", fromlist=["execute_intelligence_check"]))
    run_check("execution_optimizer_v2", lambda: __import__("core.execution_optimizer_v2", fromlist=["optimize_order_execution"]))
    run_check("self_optimizer", lambda: __import__("core.self_optimizer", fromlist=["run_self_optimization_v51"]))
    run_check("adaptive_weighting", lambda: __import__("core.adaptive_weighting", fromlist=["get_adaptive_weights"]))
    run_check("survival_intelligence", lambda: __import__("core.survival_intelligence", fromlist=["analyze_market_condition"]))
    run_check("brain_unified", lambda: __import__("core.brain_unified", fromlist=["compute_final_brain_score"]))
    run_check("decision_snapshot", lambda: __import__("core.decision_snapshot", fromlist=["initialize_snapshot_store"]))
    run_check("context_memory", lambda: __import__("core.context_memory", fromlist=["context_memory"]))
    run_check("ai_memory", lambda: __import__("core.ai_memory", fromlist=["initialize_memory"]))
    run_check("adaptive_ai", lambda: __import__("core.adaptive_ai", fromlist=["market_is_safe"]))
    run_check("startup_check", lambda: __import__("core.startup_check", fromlist=["run_startup_check"]))
    run_check("telegram_bot", lambda: __import__("core.telegram_bot", fromlist=["send_telegram_message"]))

    print("\n[ STRATEGIES ]")

    run_check("smart_money", lambda: __import__("core.smart_money", fromlist=["get_smc_signal"]))
    run_check("daily.signal", lambda: __import__("core.daily.signal", fromlist=["get_daily_signal"]))
    run_check("position.trailing", lambda: __import__("core.position_trailing", fromlist=["update_position_trailing"]))
    run_check("multi_timeframe", lambda: __import__("core.multi_timeframe", fromlist=["get_mtf_consensus"]))

    print("\n[ BRAIN ]")
    run_check("master_brain", lambda: __import__("brain.master_brain", fromlist=["master_brain_decide"]))
    run_check("trade_dna", lambda: __import__("brain.trade_dna", fromlist=["record_trade_dna"]))
    run_check("history_learner", lambda: __import__("brain.history_learner"))
    run_check("knowledge_base", lambda: __import__("brain.knowledge_base"))
    run_check("news_memory", lambda: __import__("brain.news_memory"))

    print("\n[ ML ]")
    run_check("feature_engine", lambda: __import__("ml.feature_engine", fromlist=["extract_live_features"]))
    run_check("ml_orchestrator", lambda: __import__("ml.ml_orchestrator", fromlist=["ml_evaluate_trade"]))
    run_check("xgboost_model", lambda: __import__("ml.xgboost_model"))
    run_check("neural_network", lambda: __import__("ml.neural_network"))
    run_check("reinforcement", lambda: __import__("ml.reinforcement", fromlist=["encode_state"]))

    print("\n[ V7 EXECUTION INTELLIGENCE ]")
    run_check("dynamic_confidence", lambda: __import__("core.dynamic_confidence", fromlist=["get_dynamic_confidence_threshold"]))
    run_check("missed_opportunity", lambda: __import__("core.missed_opportunity", fromlist=["record_rejection"]))
    run_check("velocity_engine", lambda: __import__("core.velocity_engine", fromlist=["analyze_velocity_from_closes"]))
    run_check("confidence_decay", lambda: __import__("core.confidence_decay", fromlist=["apply_confidence_decay"]))
    run_check("liquidity_vacuum", lambda: __import__("core.liquidity_vacuum", fromlist=["analyze_liquidity_vacuum"]))
    run_check("sweep_predictor", lambda: __import__("core.sweep_predictor", fromlist=["compute_sweep_probability"]))
    run_check("micro_trigger", lambda: __import__("core.micro_trigger", fromlist=["check_micro_trigger"]))
    run_check("v7_integration", lambda: __import__("core.v7_integration", fromlist=["v7_enabled"]))
    run_check("opportunity_engine", lambda: __import__("brain.opportunity_engine", fromlist=["evaluate_opportunity"]))
    run_check("scale_in", lambda: __import__("execution.scale_in", fromlist=["evaluate_scale_in"]))

    print("\n[ TESTING ]")
    run_check("statistics", lambda: __import__("testing.statistics", fromlist=["full_stats_analysis"]))
    run_check("backtester", lambda: __import__("testing.backtester", fromlist=["run_full_test_suite"]))
    run_check("test_v7_execution", lambda: __import__("testing.test_v7_execution_intelligence"))

    print("\n" + "=" * 50)
    print(f"✅ PASSED: {len(PASS)}")
    if FAIL:
        print(f"❌ FAILED: {len(FAIL)}")
        for label, err in FAIL:
            print(f"   • {label}: {err}")
        return 1

    print("🎉 ALL TESTS PASSED — V6.0 PRO READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
