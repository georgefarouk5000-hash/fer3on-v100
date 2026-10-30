import json

from core.exit_manager import resolve_exit_outcomes, simulate_exit_outcome


def _position():
    return {
        "direction": "BUY",
        "entry_price": 100.0,
        "sl_dist": 2.0,
        "open_time": "2026-08-20T10:00:00+00:00",
        "strategy": "SMC",
    }


def test_exit_simulator_uses_conservative_same_bar_ordering():
    result = simulate_exit_outcome(
        _position(),
        [{
            "time": "2026-08-20T10:01:00+00:00",
            "high": 110.0,
            "low": 97.0,
            "close": 104.0,
        }],
        atr=1.0,
    )

    assert result["resolved"] is True
    assert result["outcome"] == "LOSS_INTRABAR_AMBIGUOUS"
    assert result["simulated_r"] == -1.0


def test_exit_outcome_resolves_once_and_links_complete_actual_close(tmp_path):
    event_path = tmp_path / "events.jsonl"
    log_path = tmp_path / "exit.jsonl"
    events = [
        {
            "event_type": "DECISION",
            "correlation_id": "decision-1",
            "candidate_id": "candidate-1",
            "symbol": "XAUUSD",
            "strategy": "SMC",
            "signal": "BUY",
            "timestamp": "2026-08-20T10:00:00+00:00",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "atr": 1.0,
        },
        {
            "event_type": "TRADE_CLOSED",
            "correlation_id": "decision-1",
            "position_id": 41,
            "entry_cost_complete": True,
            "total_position_net_profit": -3.25,
        },
    ]
    event_path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )
    candles = [{
        "time": "2026-08-20T10:01:00+00:00",
        "high": 100.5,
        "low": 97.0,
        "close": 98.0,
    }]

    result = resolve_exit_outcomes(
        candles,
        log_path=str(log_path),
        event_path=str(event_path),
    )

    assert result["ok"] is True
    assert result["resolved"] == 1
    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["record_type"] == "EXIT_SIMULATION_OUTCOME"
    assert record["outcome"] == "LOSS"
    assert record["candidate_id"] == "candidate-1"
    assert record["actual_profit"] == -3.25
    assert record["actual_costs_complete"] is True
    assert resolve_exit_outcomes(
        candles,
        log_path=str(log_path),
        event_path=str(event_path),
    )["resolved"] == 0

