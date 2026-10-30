import json
import tempfile
from pathlib import Path

from analytics.shadow_counterfactual import log_virtual_shadow, resolve_outcomes, summary


def test_virtual_shadow_record_resolves_as_recovery_candidate():
    path = Path(tempfile.mkdtemp()) / "shadow.jsonl"
    assert log_virtual_shadow({
        "signal_id": "virtual-1",
        "direction": "BUY",
        "entry_price": 100.0,
        "sl_dist": 2.0,
        "tp_dist": 2.0,
        "signal_time": "2026-09-08T00:00:00+00:00",
        "config_revision": "recovery_atr_v1",
    }, log_path=str(path))
    result = resolve_outcomes([
        {"time": "2026-09-08T00:05:00+00:00", "high": 103.0, "low": 99.0},
    ], log_path=str(path), horizon=1)
    assert result["resolved"] == 1
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["record_type"] == "VIRTUAL_SHADOW"
    assert row["outcome"] == "WIN"
    totals = summary(log_path=str(path))
    assert totals["rejected_total"] == 0
    assert totals["virtual_total"] == 1
    assert totals["WIN"] == 0


def test_virtual_shadow_returns_false_when_log_path_is_a_directory():
    path = Path(tempfile.mkdtemp()) / "shadow.jsonl"
    path.mkdir()

    assert not log_virtual_shadow({
        "signal_id": "virtual-write-failure",
        "direction": "BUY",
        "entry_price": 100.0,
        "sl_dist": 2.0,
        "tp_dist": 2.0,
        "signal_time": "2026-09-08T00:00:00+00:00",
    }, log_path=str(path))
