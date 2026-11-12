from types import SimpleNamespace

import main
from core import demo_execution, trade_event_ledger, tsm_strategy


def test_tsm_candidate_is_logged_when_demo_execution_is_blocked(monkeypatch):
    class FakeMT5:
        TIMEFRAME_M15 = 15

        @staticmethod
        def copy_rates_from_pos(symbol, timeframe, start, count):
            return [{"time": index * 900} for index in range(512)]

        @staticmethod
        def symbol_info_tick(symbol):
            return SimpleNamespace(ask=2000.1, bid=2000.0)

    candidate = SimpleNamespace(
        signal="BUY",
        decision_bar_time="2026-11-12T00:00:00+00:00",
        entry_reason="TSM closed-bar setup",
        entry_conditions=["M5_CLOSED_CANDLE_TIMING_CONFIRMED"],
        evidence=lambda: {"timeframe": "M15"},
    )
    candidate_records = []
    events = []

    monkeypatch.setattr(main, "mt5", FakeMT5)
    monkeypatch.setattr(main, "MT5_AVAILABLE", True)
    monkeypatch.setattr(main, "TSM_RUNTIME_ENABLED", True)
    monkeypatch.setattr(main, "_last_tsm_bar_time", None)
    monkeypatch.setattr(
        main,
        "_load_tsm_context_rates",
        lambda symbol, bar_time: (([], [], []), None),
    )
    monkeypatch.setattr(
        tsm_strategy,
        "build_tsm_candidate",
        lambda *args, **kwargs: (candidate, "TSM_SIGNAL_CONFIRMED"),
    )
    monkeypatch.setattr(
        trade_event_ledger,
        "claim_candidate_record",
        lambda path, record: candidate_records.append(record) or True,
    )
    monkeypatch.setattr(
        trade_event_ledger,
        "append_trade_event",
        lambda event_type, correlation_id, **details: events.append(
            (event_type, correlation_id, details)
        ),
    )
    monkeypatch.setattr(
        demo_execution,
        "demo_execution_status",
        lambda: (False, "DEMO_TRADING_NOT_ENABLED"),
    )

    main._run_tsm("XAUUSD")

    assert len(candidate_records) == 1
    assert candidate_records[0]["status"] == "SIGNAL"
    assert candidate_records[0]["reason"] == "TSM_SIGNAL_CONFIRMED"
    assert [event[0] for event in events] == [
        "STRATEGY_CANDIDATE",
        "STRATEGY_CANDIDATE_BLOCKED",
    ]
    assert events[-1][2]["reason"] == "DEMO_EXECUTION_BLOCKED"
    assert events[-1][2]["execution_reason"] == "DEMO_TRADING_NOT_ENABLED"
