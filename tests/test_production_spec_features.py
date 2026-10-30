import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.module_registry import build_module_registry
from core.production_intelligence import (
    compute_ai_cooperation_score,
    evaluate_demo_certification,
    evaluate_promotion_requirements,
)
from core.risk_manager import evaluate_position_limits
from core.watchdog import collect_watchdog_status


def test_module_registry_reports_active_disabled_and_error_states():
    registry = build_module_registry()
    assert "unified_decision" in registry
    assert registry["unified_decision"]["status"] in {"ACTIVE", "DISABLED", "ERROR"}


def test_position_limits_block_excessive_exposure():
    result = evaluate_position_limits(strategy="SMC", current_positions=5, total_positions=8)
    assert result["allowed"] is False
    assert "SMC" in result["reason"]


def test_ai_cooperation_score_tracks_agreement():
    score = compute_ai_cooperation_score(
        memory_score=92,
        ml_score=88,
        brain_score=85,
        dna_score=90,
        execution_score=87,
        smc_score=84,
    )
    assert 80 <= score <= 100


def test_demo_certification_and_promotion_requirements_can_be_evaluated():
    demo = evaluate_demo_certification(trades=120, win_rate=0.58, profit_factor=1.45, drawdown=7.5, recovery_time=14)
    promotion = evaluate_promotion_requirements(
        trades=220,
        win_rate=0.60,
        profit_factor=1.55,
        drawdown=8.0,
        recovery_time=10,
        authority_leaks=False,
        broken_chains=False,
        critical_failures=0,
    )
    assert demo["passed"] is True
    assert promotion["passed"] is True


def test_watchdog_emits_recovery_actions_for_failures():
    status = collect_watchdog_status(mt5_available=False, memory_available=True, telegram_available=True, production_ready=True, signal_quality=70)
    assert any(action in {"AUTO_RESTART", "AUTO_RECOVERY", "PROCESS_RESCUE"} for action in status["recovery_actions"])
