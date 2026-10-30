"""Regression tests for the HISTORY_FILE (data/history/trades.csv) close-sync fix.

Bug (found while investigating why ~half of trades.csv sat at result="OPEN"
forever, and why every closed row had rr_ratio/quality_score/brain_score==0):

`sync_mt5_history()` (core/mt5_history_sync.py) already computes the correct
`close_ticket = deal.position_id or deal.ticket` for matching a closing deal
back to its open-time record — and uses it correctly for ai_memory.csv
(`deal_exists`/`save_trade_memory`) and for `record_trade_close()`. But the
HISTORY_FILE (trades.csv) write path was never updated to match: it kept
checking/writing `deal.ticket` (the closing DEAL's own id, which is not the
same id the open-time row was logged under -- see trade_executor.py, which
logs `ticket=result.order`) and it unconditionally hardcoded
rr_ratio/quality_score/brain_score to 0.

Net effect: the open-time row (with the real quality_score/rr_ratio/
brain_score captured at entry) was never found and never updated -- it sat at
result="OPEN" forever -- while a brand-new, permanently-zeroed orphan row got
appended under the closing deal's own ticket instead. Every downstream module
that tries to learn "does quality_score/rr_ratio actually predict a win"
(adaptive_learning, outcome_learning, contribution_analysis, history_learner)
was training on broken data as a result.

Fix: key the HISTORY_FILE write on close_ticket, and merge (upsert) into the
existing open-time row -- only overwriting result/profit -- instead of always
appending a fresh, zeroed-out row.
"""
import csv
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import core.data_integrity as di
import core.mt5_history_sync as sync_mod
import pytest


def _make_fake_deal(ticket, position_id, profit=45.0, comment="[tp 2415.00]"):
    return SimpleNamespace(
        entry=1,
        ticket=ticket,
        position_id=position_id,
        type=0,  # BUY
        magic=123,
        symbol="XAUUSD",
        volume=0.01,
        profit=profit,
        price=2415.0,
        time=1753300000,  # arbitrary fixed unix timestamp
        comment=comment,
    )


def _patched_sync(monkeypatch, tmp_path, deal, *, has_open_record):
    """Run sync_mt5_history() with every side-effect dependency neutralised
    except the exact HISTORY_FILE read/write path being tested."""
    history_file = str(tmp_path / "trades.csv")
    mt5_file = str(tmp_path / "mt5_trade_history.csv")

    monkeypatch.setattr(sync_mod, "HISTORY_FILE", history_file)
    monkeypatch.setattr(sync_mod, "FILE_NAME", mt5_file)
    monkeypatch.setattr(
        sync_mod, "DEAL_EVENTS_FILE", str(tmp_path / "mt5_deal_events.jsonl")
    )
    monkeypatch.setattr(
        sync_mod,
        "OPEN_RECONCILIATION_LOG",
        str(tmp_path / "open_records_shadow.jsonl"),
    )
    monkeypatch.setattr(sync_mod, "MT5_AVAILABLE", True)
    monkeypatch.setattr(sync_mod, "mt5", MagicMock(history_deals_get=lambda *a, **k: [deal]))

    monkeypatch.setattr(
        sync_mod, "resolve_trade_identity",
        lambda magic=0: {"strategy": "SMC", "magic": 123, "raw_magic": 123, "magic_mismatch": False},
    )
    monkeypatch.setattr(sync_mod, "deal_exists", lambda ticket: has_open_record)
    monkeypatch.setattr(sync_mod, "save_trade_memory", MagicMock())
    monkeypatch.setattr(sync_mod, "record_trade_outcome", MagicMock())
    monkeypatch.setattr(sync_mod, "append_trade", MagicMock())
    monkeypatch.setattr(sync_mod, "register_win", MagicMock())
    monkeypatch.setattr(sync_mod, "register_loss", MagicMock())
    monkeypatch.setattr(sync_mod, "record_trade_close", MagicMock())
    monkeypatch.setattr(sync_mod, "record_trade_partial_close", MagicMock())
    monkeypatch.setattr(sync_mod, "append_trade_event", MagicMock())
    monkeypatch.setattr(sync_mod, "update_certification_progress", lambda: {"closed_trade_count": 1})

    return history_file, mt5_file


def test_unknown_magic_recovered_via_parent_position_strategy(monkeypatch, tmp_path):
    """Regression test for the recovery fix: a deal with magic=0/unresolved
    (e.g. a partial TP-ladder close, or a manual SL/TP tweak on a
    bot-opened position) must be recovered via its parent position's
    already-recorded strategy, not silently discarded."""
    open_ticket = 77700
    orphan_deal = _make_fake_deal(ticket=99500, position_id=open_ticket, profit=12.34)
    orphan_deal.magic = 0

    history_file, _ = _patched_sync(monkeypatch, tmp_path, orphan_deal, has_open_record=True)
    # This test needs UNKNOWN specifically (unlike the shared SMC-always mock).
    monkeypatch.setattr(
        sync_mod, "resolve_trade_identity",
        lambda magic=0: {"strategy": "UNKNOWN", "magic": 0, "raw_magic": 0, "magic_mismatch": False},
    )

    di.append_csv_row(history_file, di.HISTORY_COLUMNS, {
        "date": "2026-07-23T05:00:00+00:00",
        "ticket": open_ticket,
        "signal": "BUY",
        "lot": 0.01,
        "profit": 0,
        "result": "OPEN",
        "strategy": "MICRO",
        "session": "LONDON",
        "market_regime": "TRENDING",
        "exec_grade": "A",
        "rr_ratio": 1.5,
        "quality_score": 60,
        "brain_score": 70,
    })

    sync_mod.sync_mt5_history()

    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    matching = [r for r in rows if str(r["ticket"]) == str(open_ticket)]
    assert len(matching) == 1
    assert matching[0]["strategy"] == "MICRO"
    assert matching[0]["result"] == "WIN"
    assert float(matching[0]["profit"]) == 12.34


def test_unknown_magic_with_no_parent_recorded_as_manual(monkeypatch, tmp_path):
    """A deal with no resolvable magic AND no matching parent position (a
    fully manual trade opened and closed outside the bot) must still be
    recorded -- as strategy=MANUAL -- not discarded."""
    orphan_deal = _make_fake_deal(ticket=99600, position_id=88800, profit=-7.5)
    orphan_deal.magic = 0

    history_file, _ = _patched_sync(monkeypatch, tmp_path, orphan_deal, has_open_record=False)
    monkeypatch.setattr(
        sync_mod, "resolve_trade_identity",
        lambda magic=0: {"strategy": "UNKNOWN", "magic": 0, "raw_magic": 0, "magic_mismatch": False},
    )

    sync_mod.sync_mt5_history()

    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    assert len(rows) == 1
    assert rows[0]["strategy"] == "MANUAL"
    assert rows[0]["result"] == "LOSS"
    assert float(rows[0]["profit"]) == -7.5


def test_close_merges_into_existing_open_row_preserving_scores(monkeypatch, tmp_path):
    open_ticket = 55000  # this is what result.order was at open time
    closing_deal = _make_fake_deal(ticket=99001, position_id=open_ticket)

    history_file, _ = _patched_sync(monkeypatch, tmp_path, closing_deal, has_open_record=True)

    # Seed the open-time row exactly as trade_executor.py's persist_trade_log
    # would have written it -- real quality/RR data, still "OPEN".
    di.append_csv_row(history_file, di.HISTORY_COLUMNS, {
        "date": "2026-07-23T05:00:00+00:00",
        "ticket": open_ticket,
        "signal": "BUY",
        "lot": 0.01,
        "profit": 0,
        "result": "OPEN",
        "strategy": "SMC",
        "session": "LONDON",
        "market_regime": "TRENDING",
        "exec_grade": "A",
        "rr_ratio": 2.1,
        "quality_score": 77,
        "brain_score": 88,
    })

    sync_mod.sync_mt5_history()

    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    matching = [r for r in rows if str(r["ticket"]) == str(open_ticket)]

    assert len(rows) == 1, (
        f"Expected the open row to be updated in place, got {len(rows)} rows -- "
        "a duplicate/orphan row was created instead (bug regressed)."
    )
    assert len(matching) == 1
    row = matching[0]
    assert row["result"] == "WIN"
    assert float(row["profit"]) == 45.0
    # The whole point of the fix: these must survive the close untouched.
    assert float(row["quality_score"]) == 77, "quality_score was zeroed on close -- bug regressed."
    assert float(row["rr_ratio"]) == 2.1, "rr_ratio was zeroed on close -- bug regressed."
    assert float(row["brain_score"]) == 88, "brain_score was zeroed on close -- bug regressed."
    assert row["session"] == "LONDON"
    assert row["strategy"] == "SMC"


def test_close_falls_back_to_placeholders_when_no_open_row_exists(monkeypatch, tmp_path):
    """A trade with no matching open-time record (opened manually, or before
    this bot instance ran) has nothing to merge into -- it should still get
    logged (with the documented SYNC/0 placeholders), not silently dropped."""
    open_ticket = 66000
    closing_deal = _make_fake_deal(ticket=99002, position_id=open_ticket, profit=-12.0, comment="[sl 2400.00]")

    history_file, _ = _patched_sync(monkeypatch, tmp_path, closing_deal, has_open_record=False)

    sync_mod.sync_mt5_history()

    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    assert len(rows) == 1
    row = rows[0]
    assert str(row["ticket"]) == str(open_ticket)
    assert row["result"] == "LOSS"
    assert float(row["profit"]) == -12.0
    assert row["exec_grade"] == "SYNC"


def test_history_sync_baseline_skips_positions_opened_before_reset(monkeypatch, tmp_path):
    old_position_id = 70001
    new_position_id = 70002
    baseline_file = tmp_path / "history_sync_baseline.json"
    baseline_file.write_text(
        '{"ignore_positions_opened_before":"1970-01-01T00:16:40+00:00"}',
        encoding="utf-8",
    )

    old_open = SimpleNamespace(
        entry=0, position_id=old_position_id, volume=0.01, price=2400.0, time=900,
    )
    new_open = SimpleNamespace(
        entry=0, position_id=new_position_id, volume=0.01, price=2400.0, time=1010,
    )
    old_close = _make_fake_deal(ticket=99010, position_id=old_position_id, profit=25.0)
    old_close.time = 1100
    new_close = _make_fake_deal(ticket=99020, position_id=new_position_id, profit=30.0)
    new_close.time = 1120

    history_file, _ = _patched_sync(
        monkeypatch, tmp_path, new_close, has_open_record=False
    )
    monkeypatch.setattr(
        sync_mod,
        "DEAL_EVENTS_FILE",
        str(tmp_path / "mt5_deal_events.jsonl"),
    )
    monkeypatch.setattr(
        sync_mod,
        "OPEN_RECONCILIATION_LOG",
        str(tmp_path / "open_records_shadow.jsonl"),
    )
    sync_mod.mt5.history_deals_get = lambda *args, **kwargs: [
        old_open, old_close, new_open, new_close,
    ]

    result = sync_mod.sync_mt5_history()

    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    assert result["synced"] == 1
    assert [int(row["ticket"]) for row in rows] == [new_position_id]
    assert result["close_events"] == [{
        "ticket": new_position_id,
        "deal_ticket": new_close.ticket,
        "profit": new_close.profit,
        "timestamp": "1970-01-01T00:18:40+00:00",
        "result": "WIN",
        "decision_id": "",
        "entry_reason": "",
        "entry_conditions": [],
        "entry_cost_complete": True,
    }]


def test_position_summary_aggregates_entry_and_partial_exit_costs():
    opening = SimpleNamespace(
        entry=0,
        ticket=10000,
        order=10000,
        position_id=10000,
        volume=0.1,
        price=2000.0,
        profit=0.0,
        commission=-1.0,
        swap=0.0,
        fee=0.0,
        time=1000,
    )
    partial = _make_fake_deal(ticket=10001, position_id=10000, profit=20.0)
    partial.entry = 1
    partial.type = 1
    partial.volume = 0.04
    partial.price = 2010.0
    partial.commission = -0.4
    partial.swap = -0.1
    final = _make_fake_deal(ticket=10002, position_id=10000, profit=-30.0)
    final.entry = 1
    final.type = 1
    final.volume = 0.06
    final.price = 1995.0
    final.commission = -0.6
    final.swap = -0.2

    summaries, events = sync_mod._build_position_summaries([opening, partial, final])

    assert summaries[10000]["total_net_profit"] == -12.3
    assert events[10001]["net_profit"] == 19.1
    assert events[10001]["cumulative_net_profit"] == 19.1
    assert events[10001]["is_final_close"] is False
    assert events[10002]["net_profit"] == pytest.approx(-31.4)
    assert events[10002]["cumulative_net_profit"] == -12.3
    assert events[10002]["is_final_close"] is True


def test_partial_closes_sync_as_one_net_position_result_and_correlated_events(
    monkeypatch, tmp_path
):
    position_id = 61234
    decision_id = "0123456789abcdef01234567"
    opening = SimpleNamespace(
        entry=0,
        ticket=position_id,
        order=position_id,
        position_id=position_id,
        type=0,
        magic=123,
        symbol="XAUUSD",
        volume=0.1,
        price=2000.0,
        profit=0.0,
        commission=-1.0,
        swap=0.0,
        fee=0.0,
        time=1753300000,
        comment=f"F3-S-{decision_id}",
    )
    partial = _make_fake_deal(ticket=71001, position_id=position_id, profit=20.0)
    partial.type = 1
    partial.volume = 0.04
    partial.price = 2010.0
    partial.commission = -0.4
    partial.swap = -0.1
    final = _make_fake_deal(ticket=71002, position_id=position_id, profit=-30.0)
    final.type = 1
    final.volume = 0.06
    final.price = 1995.0
    final.commission = -0.6
    final.swap = -0.2
    history_file, mt5_file = _patched_sync(
        monkeypatch, tmp_path, final, has_open_record=True
    )
    sync_mod.mt5.history_deals_get = lambda *args, **kwargs: [
        opening, partial, final,
    ]
    di.append_csv_row(history_file, di.HISTORY_COLUMNS, {
        "date": "2026-07-23T05:00:00+00:00",
        "ticket": position_id,
        "signal": "BUY",
        "lot": 0.1,
        "profit": 0,
        "result": "OPEN",
        "strategy": "SMC",
        "session": "LONDON",
        "market_regime": "TRENDING",
        "exec_grade": "A",
        "rr_ratio": 2.0,
        "quality_score": 80,
        "brain_score": 85,
        "decision_id": decision_id,
        "entry_reason": "SMC: BOS + FVG + RETEST",
        "entry_conditions": '["BOS", "FVG", "RETEST"]',
        "entry_price": 2000.0,
        "stop_price": 1980.0,
        "target_price": 2040.0,
        "stop_source": "structure",
        "stop_anchor_price": 1990.0,
        "stop_anchor_index": 23,
        "stop_anchor_label": "HL",
        "stop_reason": "LAST_CONFIRMED_HIGHER_LOW",
        "stop_buffer": 2.0,
    })

    result = sync_mod.sync_mt5_history()
    rows = di.read_csv_records(history_file, di.HISTORY_COLUMNS)
    with open(mt5_file, encoding="utf-8", newline="") as handle:
        mt5_rows = list(csv.DictReader(handle))

    assert result["close_events"][0]["profit"] == -12.3
    assert result["close_events"][0]["decision_id"] == decision_id
    assert result["close_events"][0]["entry_reason"] == "SMC: BOS + FVG + RETEST"
    assert result["close_events"][0]["entry_conditions"] == ["BOS", "FVG", "RETEST"]
    assert len(rows) == 1
    assert rows[0]["result"] == "LOSS"
    assert float(rows[0]["profit"]) == -12.3
    assert rows[0]["decision_id"] == decision_id
    assert rows[0]["entry_cost_complete"] == "True"
    assert len(mt5_rows) == 2
    assert [float(row["position_net_profit"]) for row in mt5_rows] == [19.1, -12.3]
    assert mt5_rows[-1]["entry_cost_complete"] == "True"
    assert float(mt5_rows[-1]["position_commission"]) == -2.0
    assert float(mt5_rows[-1]["position_swap"]) == -0.3
    assert sync_mod.record_trade_partial_close.call_args.kwargs["profit"] == 19.1
    assert sync_mod.record_trade_close.call_args.kwargs["profit"] == -31.4
    sync_mod.register_loss.assert_called_once_with(-12.3)
    record = sync_mod.append_trade.call_args.args[0]
    assert record.ticket == position_id
    assert record.profit == -12.3
    assert record.entry_price == 2000.0
    assert record.entry_reason == "SMC: BOS + FVG + RETEST"
    assert record.entry_conditions == ["BOS", "FVG", "RETEST"]
    assert record.exit_price == 2001.0
    assert record.lot == 0.1
    assert record.extra["decision_id"] == decision_id
    assert record.extra["entry_reason"] == "SMC: BOS + FVG + RETEST"
    assert record.extra["entry_conditions"] == ["BOS", "FVG", "RETEST"]
    assert record.extra["commission"] == -2.0
    assert record.extra["swap"] == -0.3
    assert record.extra["stop_anchor_label"] == "HL"
    assert sync_mod.append_trade_event.call_count == 2
    assert {
        call.args[1]
        for call in sync_mod.append_trade_event.call_args_list
    } == {decision_id}

    second_result = sync_mod.sync_mt5_history()
    assert second_result["close_events"] == []
    assert sync_mod.append_trade.call_count == 1
    assert sync_mod.record_trade_partial_close.call_count == 1
    assert sync_mod.record_trade_close.call_count == 1


def test_truth_layer_record_keyed_by_position_ticket_not_deal_ticket(monkeypatch, tmp_path):
    """Regression test for a data-integrity bug found while investigating why
    analytics/csv_truth_bridge.py::sync_csv_to_truth_layer() kept re-"syncing"
    trades that mt5_history_sync() had already recorded: the truth_layer
    TradeRecord was keyed by deal.ticket (the closing DEAL's own id), while
    trades.csv (and everything the bridge dedupes against) is keyed by
    close_ticket (= position_id, the POSITION ticket). Confirmed empirically
    against real data: zero ticket overlap between the two files for the
    same 20 real trades -- every trade was silently duplicated into
    truth_layer with a blank build_id the first time both sync paths ran in
    the same session.

    Fix: TradeRecord.ticket must equal close_ticket (same value written to
    trades.csv), not deal.ticket.
    """
    open_ticket = 77000  # position ticket -- what trade_executor.py logged at open
    deal_ticket = 88123  # the CLOSING deal's own id -- must NOT end up as TradeRecord.ticket
    closing_deal = _make_fake_deal(ticket=deal_ticket, position_id=open_ticket, profit=30.0)

    history_file, _ = _patched_sync(monkeypatch, tmp_path, closing_deal, has_open_record=True)

    di.append_csv_row(history_file, di.HISTORY_COLUMNS, {
        "date": "2026-07-23T05:00:00+00:00",
        "ticket": open_ticket,
        "signal": "BUY",
        "lot": 0.01,
        "profit": 0,
        "result": "OPEN",
        "strategy": "SMC",
        "session": "LONDON",
        "market_regime": "TRENDING",
        "exec_grade": "A",
        "rr_ratio": 2.1,
        "quality_score": 77,
        "brain_score": 88,
    })

    sync_mod.sync_mt5_history()

    # append_trade is mocked in _patched_sync -- inspect what it was called with.
    assert sync_mod.append_trade.call_count == 1
    record = sync_mod.append_trade.call_args[0][0]
    assert record.ticket == open_ticket, (
        f"TradeRecord.ticket={record.ticket} -- expected close_ticket={open_ticket} "
        f"(must match trades.csv's key), not deal_ticket={deal_ticket}. Bug regressed."
    )
