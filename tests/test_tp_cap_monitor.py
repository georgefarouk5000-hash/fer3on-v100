import os

from analytics.tp_cap_monitor import record_tp_cap_event, load_tp_cap_events, tp_cap_summary


def test_record_and_load(tmp_path):
    csv_path = str(tmp_path / "tp_cap_events.csv")

    ok = record_tp_cap_event(
        strategy="SMC", signal="BUY", atr=1.5, sl_dist=3.0,
        tp_dist_requested=12.0, tp_dist_capped=9.0,
        cap_multiplier_atr=3.0, cap_multiplier_sl=2.5,
        csv_path=csv_path,
    )
    assert ok is True
    assert os.path.exists(csv_path)

    events = load_tp_cap_events(csv_path)
    assert len(events) == 1
    assert events[0]["strategy"] == "SMC"
    assert float(events[0]["clip_pct"]) == 25.0  # (1 - 9/12) * 100


def test_summary_aggregates_by_strategy(tmp_path):
    csv_path = str(tmp_path / "tp_cap_events.csv")

    record_tp_cap_event(
        strategy="SMC", signal="BUY", atr=1.0, sl_dist=2.0,
        tp_dist_requested=10.0, tp_dist_capped=5.0,
        cap_multiplier_atr=3.0, cap_multiplier_sl=2.5, csv_path=csv_path,
    )
    record_tp_cap_event(
        strategy="SMC", signal="SELL", atr=1.0, sl_dist=2.0,
        tp_dist_requested=10.0, tp_dist_capped=8.0,
        cap_multiplier_atr=3.0, cap_multiplier_sl=2.5, csv_path=csv_path,
    )
    record_tp_cap_event(
        strategy="DAILY", signal="BUY", atr=2.0, sl_dist=4.0,
        tp_dist_requested=30.0, tp_dist_capped=24.0,
        cap_multiplier_atr=6.0, cap_multiplier_sl=3.0, csv_path=csv_path,
    )

    summary = tp_cap_summary(csv_path)
    assert summary["total_events"] == 3
    assert summary["by_strategy"]["SMC"]["count"] == 2
    assert summary["by_strategy"]["DAILY"]["count"] == 1


def test_load_missing_file_returns_empty(tmp_path):
    csv_path = str(tmp_path / "does_not_exist.csv")
    assert load_tp_cap_events(csv_path) == []
    assert tp_cap_summary(csv_path) == {"total_events": 0, "by_strategy": {}}
