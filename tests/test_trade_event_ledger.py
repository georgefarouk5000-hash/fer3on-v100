import json

from core import trade_event_ledger


def test_trade_correlation_id_is_stable_for_same_decision():
    decision = {
        "symbol": "XAUUSD",
        "strategy": "SMC",
        "signal": "BUY",
        "decision_bar_time": 1753300000,
        "entry_price": 2000.0,
        "stop_loss": 1980.0,
        "take_profit": 2040.0,
    }

    first = trade_event_ledger.create_trade_correlation_id(**decision)
    second = trade_event_ledger.create_trade_correlation_id(**decision)
    changed = trade_event_ledger.create_trade_correlation_id(
        **{**decision, "stop_loss": 1979.0}
    )

    assert first == second
    assert len(first) == 24
    assert first != changed


def test_mt5_comment_keeps_full_correlation_id_within_broker_limit():
    correlation_id = "0123456789abcdef01234567"

    comment = trade_event_ledger.build_mt5_trade_comment(
        "DAILY",
        correlation_id,
    )

    assert comment == f"F3-D-{correlation_id}"
    assert len(comment) <= 31


def test_snapshot_entry_attribution_records_confirmed_conditions_only():
    attribution = trade_event_ledger.build_entry_attribution(
        {
            "strategy": "SMC",
            "entry_grade": "A",
            "smc_details": {
                "sweep": True,
                "bos": True,
                "fvg": True,
                "ob": False,
                "mitigation": False,
                "breaker": False,
                "retest": True,
                "premium_discount_aligned": False,
            },
            "structure": {
                "structure": "TRANSITION_BULLISH",
                "bias": "BUY",
                "mtf_aligned": True,
            },
            "candle": {"confirmed": True},
            "quality_gate": {"mode": "PASS"},
            "confidence": {"pct": 72},
        },
        {"verdict": "PASS_FULL", "reasons": ["STRUCTURE_CONFIRMED"]},
    )

    assert attribution["entry_conditions"] == [
        "LIQUIDITY_SWEEP",
        "BOS",
        "FVG",
        "RETEST",
        "CHOCH",
        "CANDLE_CONFIRMATION",
        "MTF_ALIGNMENT",
    ]
    assert attribution["entry_reason"] == (
        "SMC: LIQUIDITY_SWEEP + BOS + FVG + RETEST + CHOCH + "
        "CANDLE_CONFIRMATION + MTF_ALIGNMENT"
    )
    assert attribution["entry_evidence"]["authority"]["verdict"] == "PASS_FULL"


def test_snapshot_correlation_matches_trade_geometry():
    snapshot = {
        "signal": "BUY",
        "decision_bar_time": 1753300000,
        "entry_price": 2000.0,
        "sl_dist": 20.0,
        "tp_dist": 40.0,
    }

    from_snapshot = trade_event_ledger.create_snapshot_correlation_id(
        snapshot, symbol="XAUUSD", strategy="SMC"
    )
    from_order = trade_event_ledger.create_trade_correlation_id(
        symbol="XAUUSD",
        strategy="SMC",
        signal="BUY",
        decision_bar_time=1753300000,
        entry_price=2000.0,
        stop_loss=1980.0,
        take_profit=2040.0,
    )

    assert from_snapshot == from_order


def test_candidate_id_is_stable_per_closed_bar_and_requires_bar_time():
    candidate = trade_event_ledger.create_candidate_id(
        symbol="XAUUSD",
        strategy="SMC",
        signal="BUY",
        decision_bar_time="2026-10-30T09:00:00+00:00",
    )

    assert candidate
    assert candidate == trade_event_ledger.create_candidate_id(
        symbol="xauusd",
        strategy="smc",
        signal="buy",
        decision_bar_time="2026-10-30T09:00:00+00:00",
    )
    assert candidate != trade_event_ledger.create_candidate_id(
        symbol="XAUUSD",
        strategy="SMC",
        signal="BUY",
        decision_bar_time="2026-10-30T09:05:00+00:00",
    )
    assert trade_event_ledger.create_candidate_id(
        symbol="XAUUSD",
        strategy="SMC",
        signal="BUY",
        decision_bar_time=None,
    ) == ""


def test_candidate_records_are_idempotent_after_restart(tmp_path):
    event_file = tmp_path / "candidates.jsonl"
    record = {"candidate_id": "candidate-1", "score": 50}

    assert trade_event_ledger.append_candidate_record(str(event_file), record)
    trade_event_ledger._KNOWN_CANDIDATE_LOGS.pop(str(event_file.resolve()), None)
    assert trade_event_ledger.append_candidate_record(
        str(event_file), {**record, "score": 99}
    )
    rows = [
        json.loads(line)
        for line in event_file.read_text(encoding="utf-8").splitlines()
    ]

    assert rows == [record]


def test_claim_candidate_record_is_single_owner_and_survives_restart(tmp_path):
    event_file = tmp_path / "claimed-candidates.jsonl"
    record = {"candidate_id": "candidate-claimed", "score": 50}
    target = str(event_file.resolve())
    trade_event_ledger._CLAIMED_CANDIDATE_LOGS.pop(target, None)

    assert trade_event_ledger.claim_candidate_record(str(event_file), record)
    assert not trade_event_ledger.claim_candidate_record(
        str(event_file), {**record, "score": 99}
    )
    trade_event_ledger._CLAIMED_CANDIDATE_LOGS.pop(target, None)
    assert not trade_event_ledger.claim_candidate_record(str(event_file), record)
    rows = [
        json.loads(line)
        for line in event_file.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [record]


def test_event_ledger_appends_correlated_jsonl_records(monkeypatch, tmp_path):
    event_file = tmp_path / "trade_events.jsonl"
    monkeypatch.setattr(trade_event_ledger, "TRADE_EVENTS_FILE", str(event_file))

    trade_event_ledger.append_trade_event(
        "DECISION",
        "decision-123",
        symbol="XAUUSD",
        strategy="SMC",
    )
    trade_event_ledger.append_trade_event(
        "TRADE_CLOSED",
        "decision-123",
        position_id=4321,
        net_profit=-12.3,
    )

    records = [
        json.loads(line)
        for line in event_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event_type"] for record in records] == [
        "DECISION",
        "TRADE_CLOSED",
    ]
    assert {record["correlation_id"] for record in records} == {"decision-123"}
    assert records[1]["net_profit"] == -12.3
