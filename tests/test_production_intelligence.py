import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.production_intelligence import (
    compute_signal_quality_score,
    update_signal_quality_metrics,
    evaluate_production_readiness,
    build_production_metrics_snapshot,
    write_production_dashboard,
    refresh_production_dashboard,
)
from core.watchdog import collect_watchdog_status


def test_signal_quality_score_rises_with_good_outcome():
    score = compute_signal_quality_score(
        composite_score=82,
        recent_wr=0.70,
        recent_expectancy=1.5,
        execution_quality=85,
        outcome="win",
    )
    assert score >= 80


def test_signal_quality_metrics_record_and_persist(tmp_path):
    metrics_path = tmp_path / "production_metrics.json"
    result = update_signal_quality_metrics(
        strategy="SMC",
        signal="BUY",
        composite_score=78,
        recent_wr=0.65,
        recent_expectancy=0.8,
        execution_quality=82,
        outcome="win",
        metrics_path=str(metrics_path),
    )
    assert result["signal_quality"] >= 75
    assert result["outcome"] == "win"
    assert metrics_path.exists()


def test_production_readiness_blocks_on_weak_performance():
    status = evaluate_production_readiness(
        recent_wr=0.30,
        recent_expectancy=-0.8,
        max_drawdown=8.0,
        signal_quality=45,
        open_risk=0.9,
    )
    assert status["safe_to_trade"] is False
    assert status["risk_level"] == "HIGH"


def test_metrics_snapshot_contains_professional_metrics():
    snapshot = build_production_metrics_snapshot(
        recent_wr=0.61,
        recent_expectancy=0.4,
        max_drawdown=3.2,
        signal_quality=78,
        open_risk=0.35,
    )
    assert snapshot["win_rate"] == 61.0
    assert snapshot["signal_quality"] == 78
    assert snapshot["safe_to_trade"] is True
    assert "risk_level" in snapshot


def test_production_dashboard_is_generated(tmp_path):
    output_path = tmp_path / "production_dashboard.md"
    result = write_production_dashboard(
        snapshot={
            "win_rate": 61.0,
            "expectancy": 0.4,
            "max_drawdown": 3.2,
            "signal_quality": 78,
            "open_risk": 0.35,
            "safe_to_trade": True,
            "risk_level": "LOW",
        },
        output_path=str(output_path),
    )
    assert output_path.exists()
    assert "PRODUCTION AUTOMATION DASHBOARD" in output_path.read_text(encoding="utf-8")
    assert result["dashboard_file"] == str(output_path)


def test_refresh_production_dashboard_writes_snapshot(tmp_path):
    output_path = tmp_path / "production_dashboard.md"
    result = refresh_production_dashboard(
        recent_wr=0.58,
        recent_expectancy=0.35,
        max_drawdown=2.9,
        signal_quality=74,
        open_risk=0.28,
        output_path=str(output_path),
    )
    assert output_path.exists()
    assert result["safe_to_trade"] is True
    assert result["risk_level"] in {"LOW", "MEDIUM"}
    assert result["signal_quality"] == 74


def test_watchdog_reports_production_gate_status():
    status = collect_watchdog_status(
        mt5_available=True,
        memory_available=True,
        telegram_available=True,
        cpu_ok=True,
        db_ok=True,
        production_ready=True,
        signal_quality=76,
    )
    assert status["production_ready"] is True
    assert status["automation_status"] == "READY"
    assert status["signal_quality"] == 76
