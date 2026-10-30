import json

from analytics.shadow_learning_engine import ShadowLearningEngine
from core.performance_monitoring_dashboard import PerformanceMonitoringDashboard


def _signal(outcome, **overrides):
    signal = {
        "record_type": "REJECTED_SHADOW",
        "signal_id": f"sig-{outcome}",
        "direction": "BUY",
        "regime": "TRENDING",
        "strategy": "SMC",
        "session": "LONDON",
        "confidence": 75,
        "quality_score": 80,
        "gate_stage": "quality_gate",
        "reject_reason": "QUALITY_GATE",
        "sl_dist": 2.0,
        "tp_dist": 3.0,
        "outcome": outcome,
        "outcome_bar": 4,
    }
    signal.update(overrides)
    return signal


def test_training_examples_use_candle_resolved_outcomes_not_simulation():
    engine = ShadowLearningEngine.__new__(ShadowLearningEngine)
    signals = [
        _signal("WIN"),
        _signal("LOSS"),
        _signal("LOSS_INTRABAR_AMBIGUOUS"),
        _signal("TIMEOUT"),
    ]

    records = engine.extract_training_data(signals)

    assert [record["observed_win"] for record in records] == [True, False, False, False]
    assert [record["outcome_price_distance_pnl"] for record in records] == [
        3.0, -2.0, -2.0, 0.0,
    ]
    assert {record["outcome_source"] for record in records} == {"CANDLE_RESOLVER"}
    assert all("simulated_win" not in record for record in records)
    assert records[0]["reject_gate"] == "quality_gate"


def test_pending_and_virtual_records_are_not_learning_examples():
    engine = ShadowLearningEngine.__new__(ShadowLearningEngine)
    signals = [
        _signal("PENDING"),
        _signal("WIN", record_type="VIRTUAL_SHADOW"),
        _signal("WIN", sl_dist=0),
        _signal("WIN"),
    ]

    resolved = engine.resolved_rejected_signals(signals)

    assert resolved == [signals[-1]]


def test_learning_recommendations_wait_for_minimum_resolved_sample():
    engine = ShadowLearningEngine.__new__(ShadowLearningEngine)
    engine.min_samples = 3
    records = engine.extract_training_data([_signal("WIN"), _signal("LOSS")])

    insights = engine.generate_learning_insights({}, records)

    assert insights["sample_count"] == 2
    assert insights["ready_for_recommendations"] is False
    assert insights["recommendations"] == []


def test_empty_ledger_replaces_stale_training_outputs_with_insufficient_status(tmp_path):
    engine = ShadowLearningEngine.__new__(ShadowLearningEngine)
    engine.rejected_file = tmp_path / "rejected.jsonl"
    engine.training_output = tmp_path / "training_dataset.jsonl"
    engine.insights_output = tmp_path / "learning_insights.json"
    engine.min_samples = 100
    engine.training_output.write_text('{"simulated_win": true}\n', encoding="utf-8")
    engine.insights_output.write_text('{"simulated_statistics": {"win_rate": 1.0}}', encoding="utf-8")

    result = engine.run()

    saved_insights = json.loads(engine.insights_output.read_text(encoding="utf-8"))
    assert result["status"] == "insufficient_data"
    assert saved_insights["status"] == "insufficient_data"
    assert saved_insights["recommendations"] == []
    assert engine.training_output.read_text(encoding="utf-8") == ""


def test_dashboard_does_not_present_legacy_simulated_metrics_as_observed(tmp_path):
    insights_path = (
        tmp_path / "data" / "analytics" / "shadow_learning" / "learning_insights.json"
    )
    insights_path.parent.mkdir(parents=True)
    insights_path.write_text(
        json.dumps({"simulated_statistics": {"win_rate": 0.6005}}),
        encoding="utf-8",
    )

    dashboard_path = PerformanceMonitoringDashboard(str(tmp_path)).create_html_dashboard()
    html = dashboard_path.read_text(encoding="utf-8")

    assert "LEGACY DATA NOT VERIFIED" in html
    assert "Simulated Win Rate" not in html
    assert "60.05%" not in html


def test_dashboard_displays_observed_shadow_metrics_from_resolved_samples(tmp_path):
    insights_path = (
        tmp_path / "data" / "analytics" / "shadow_learning" / "learning_insights.json"
    )
    insights_path.parent.mkdir(parents=True)
    insights_path.write_text(
        json.dumps(
            {
                "status": "success",
                "sample_count": 100,
                "ready_for_recommendations": True,
                "observed_statistics": {
                    "win_rate": 0.6,
                    "average_outcome_price_distance": 0.25,
                    "avg_rr_ratio": 1.5,
                },
                "recommendations": [],
            }
        ),
        encoding="utf-8",
    )

    dashboard_path = PerformanceMonitoringDashboard(str(tmp_path)).create_html_dashboard()
    html = dashboard_path.read_text(encoding="utf-8")

    assert "Candle-Resolved Signals" in html
    assert "Observed Win Rate" in html
    assert "60.00%" in html
    assert "0.25 / 1.50" in html


def test_dashboard_uses_current_truth_layer_metrics_not_fixed_baseline(tmp_path, monkeypatch):
    from analytics.truth_layer import TradeRecord

    trades = [
        TradeRecord(
            ticket=1,
            strategy="SMC",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            close_time="2026-01-01T10:00:00+00:00",
            profit=10,
            is_win=True,
        ),
        TradeRecord(
            ticket=2,
            strategy="SMC",
            direction="SELL",
            session="LONDON",
            regime="TRENDING",
            close_time="2026-01-01T11:00:00+00:00",
            profit=-5,
            is_win=False,
        ),
    ]
    monkeypatch.setattr(
        "analytics.performance_repository.get_all_trades",
        lambda: trades,
    )

    dashboard = PerformanceMonitoringDashboard(str(tmp_path))
    html_path = dashboard.create_html_dashboard()
    report = dashboard.generate_performance_report()
    html = html_path.read_text(encoding="utf-8")

    assert "50.00%" in html
    assert "Net P&amp;L" in html
    assert "64.0%" not in html
    assert "4.105" not in html
    assert "CURRENT-BUILD CLOSED-TRADE PERFORMANCE" in report
    assert "Closed Trades:      2" in report
    assert "Not evaluated: no validated performance alert thresholds" in report
