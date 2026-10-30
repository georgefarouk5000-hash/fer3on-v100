from core.module_registry import build_runtime_state
from core.production_intelligence import (
    compute_ai_cooperation_score,
    evaluate_demo_certification,
    evaluate_promotion_requirements,
)
from core.risk_manager import evaluate_position_limits
from core.watchdog import collect_watchdog_status


def run_spec_runtime(*, mt5_available=True, memory_available=True, telegram_available=True, production_ready=True, signal_quality=100):
    runtime_state = build_runtime_state()
    watchdog = collect_watchdog_status(
        mt5_available=mt5_available,
        memory_available=memory_available,
        telegram_available=telegram_available,
        production_ready=production_ready,
        signal_quality=signal_quality,
    )
    return {
        "runtime_state": runtime_state,
        "watchdog": watchdog,
        "position_limits": evaluate_position_limits(strategy="SMC", current_positions=4, total_positions=7),
        "cooperation_score": compute_ai_cooperation_score(
            memory_score=90,
            ml_score=88,
            brain_score=85,
            dna_score=89,
            execution_score=86,
            smc_score=84,
        ),
        "demo_certification": evaluate_demo_certification(trades=120, win_rate=0.58, profit_factor=1.45, drawdown=7.5, recovery_time=14),
        "promotion_requirements": evaluate_promotion_requirements(
            trades=220,
            win_rate=0.60,
            profit_factor=1.55,
            drawdown=8.0,
            recovery_time=10,
            authority_leaks=False,
            broken_chains=False,
            critical_failures=0,
        ),
    }
