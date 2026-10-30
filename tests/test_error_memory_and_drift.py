import json

from analytics.execution_quality import record_execution_outcome, summarize_execution_quality
from analytics.performance_drift import detect_performance_drift
from analytics.shadow_context_collector import (
    record_performance_snapshot,
    record_regime_observation,
)
from core.context_memory import ContextMemory
from core.error_memory import record_error_episode


def test_error_memory_is_shadow_only(tmp_path):
    path = tmp_path / "errors.jsonl"
    assert record_error_episode(category="SL_TOO_TIGHT", outcome="LOSS", strategy="SMC", path=str(path))
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["shadow_only"] is True
    assert record["category"] == "SL_TOO_TIGHT"


def test_context_memory_isolated_by_strategy(tmp_path):
    memory = ContextMemory()
    memory._path = str(tmp_path / "context.json")
    memory.update("LONDON", "BUY", "TRENDING", 8, "WIN", strategy="SMC")
    memory.update("LONDON", "BUY", "TRENDING", 8, "LOSS", strategy="MICRO")
    assert memory._key("LONDON", "BUY", "TRENDING", 8, "SMC") != memory._key("LONDON", "BUY", "TRENDING", 8, "MICRO")


def test_execution_quality_can_filter_strategy(tmp_path):
    path = tmp_path / "execution.csv"
    assert record_execution_outcome(1, 100, 100.2, "2026-09-02T10:00:00+00:00", "2026-09-02T10:00:01+00:00", False, csv_path=str(path), strategy="SMC")
    assert record_execution_outcome(2, 100, 100.8, "2026-09-02T10:00:00+00:00", "2026-09-02T10:00:01+00:00", False, csv_path=str(path), strategy="MICRO")
    summary = summarize_execution_quality(str(path), strategy="SMC")
    assert summary.total_records == 1
    assert summary.avg_slippage == 0.2


def test_performance_drift_is_contextual_and_shadow_only():
    records = [{"strategy": "SMC", "regime": "TRENDING", "session": "LONDON", "result": "WIN"}] * 10
    records += [{"strategy": "SMC", "regime": "TRENDING", "session": "LONDON", "result": "LOSS"}] * 10
    result = detect_performance_drift(records, baseline_size=20, recent_size=10, min_samples=5, win_rate_drop=0.5)
    assert result["mode"] == "SHADOW"
    assert result["alert_count"] == 1


def test_performance_drift_waits_for_samples():
    result = detect_performance_drift([{"strategy": "SMC", "result": "LOSS"}] * 3, min_samples=5)
    assert result["alert_count"] == 0


def test_shadow_context_collector_marks_records_shadow_only(tmp_path):
    path = tmp_path / "context.jsonl"
    assert record_regime_observation(
        symbol="XAUUSD", primary_regime="TRENDING",
        recommended_strategy="SMC", strategy_confidence=0.8,
        observed_strategy="SMC", session="LONDON", path=str(path)
    )
    assert record_performance_snapshot(
        [{"result": "WIN"}, {"result": "LOSS"}], path=str(path)
    )
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(record["shadow_only"] is True for record in records)
    assert records[-1]["samples"] == 2