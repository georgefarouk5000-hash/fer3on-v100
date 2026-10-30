from types import SimpleNamespace
from datetime import datetime, timezone
import json

import numpy as np

from analytics.shadow_counterfactual import log_rejected_shadow, resolve_outcomes
from core.entry_controller import scan_opportunity_zones
from core.main_helpers import get_rate_close, get_rate_value, rates_to_candles


def test_rate_value_reads_mapping_and_object_fields():
    assert get_rate_value({"time": 123, "high": 2.5}, "time") == 123
    assert get_rate_value(SimpleNamespace(low=1.5), "low") == 1.5
    assert get_rate_close({"close": 10.25}) == 10.25


def test_rate_value_reads_mt5_numpy_structured_records():
    rates = np.array(
        [(1793350000, 4000.0, 3990.0, 3995.0)],
        dtype=[
            ("time", "i8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
        ],
    )
    rate = rates[0]

    assert get_rate_value(rate, "time") == 1793350000
    assert get_rate_value(rate, "high") == 4000.0
    assert get_rate_value(rate, "low") == 3990.0
    assert get_rate_close(rate) == 3995.0
    assert rates_to_candles(rates) == [{
        "time": "2026-10-30T08:46:40+00:00",
        "high": 4000.0,
        "low": 3990.0,
        "close": 3995.0,
    }]


def test_numpy_rates_resolve_shadow_outcome_end_to_end(tmp_path):
    start = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).timestamp()
    rates = np.array(
        [
            (int(start + 60), 105.0, 101.0, 104.0),
            (int(start + 120), 105.0, 101.0, 104.0),
        ],
        dtype=[
            ("time", "i8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
        ],
    )
    path = tmp_path / "shadow.jsonl"
    record = {
        "signal_id": "numpy-candidate",
        "candidate_id": "numpy-candidate",
        "symbol": "XAUUSD",
        "strategy": "SMC",
        "direction": "BUY",
        "signal_time": "2026-08-20T10:00:00+00:00",
        "decision_bar_time": "2026-08-20T09:55:00+00:00",
        "entry_price": 100.0,
        "sl_dist": 2.0,
        "tp_dist": 4.0,
        "reject_reason": "TEST",
    }

    assert log_rejected_shadow(record, log_path=str(path))
    result = resolve_outcomes(rates_to_candles(rates), log_path=str(path), horizon=2)

    assert result["resolved"] == 1
    resolved = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert resolved["outcome"] == "WIN"


def test_proactive_entry_scan_accepts_numpy_structured_rates():
    rates = np.array(
        [(1793350000, 100.5, 99.5, 100.0)],
        dtype=[
            ("time", "i8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
        ],
    )

    plans = scan_opportunity_zones(
        symbol="XAUUSD",
        rates=rates,
        atr=1.0,
        structure_analysis={
            "structure_bias": "BUY",
            "swing_lows": [{"price": 99.0}],
        },
        strategy="SMC",
    )

    assert len(plans) == 1
    assert plans[0]["candidate_id"]
    assert plans[0]["decision_bar_time"] == "2026-10-30T08:46:40+00:00"
