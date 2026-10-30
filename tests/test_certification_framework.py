from certification.framework import build_certification_snapshot, update_certification_progress
from core.data_integrity import HISTORY_COLUMNS, HISTORY_FILE, dump_rows
from core.settings import BUILD_ID


def test_certification_updates_from_closed_trades(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [
        {
            "date": f"2026-06-15T00:{i:02d}:00+00:00",
            "ticket": str(i),
            "signal": "BUY",
            "lot": 0.01,
            "profit": 10 if i % 2 == 0 else -5,
            "result": "WIN" if i % 2 == 0 else "LOSS",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        }
        for i in range(1, 11)
    ]
    dump_rows(HISTORY_FILE, HISTORY_COLUMNS, rows)
    snapshot = update_certification_progress()
    assert snapshot["closed_trade_count"] == 10
    assert snapshot["levels"][0]["progress_trades"] == 10
    rebuilt = build_certification_snapshot()
    assert rebuilt["overall_metrics"]["profit_factor"] > 0


def test_certification_excludes_other_build_ids(tmp_path, monkeypatch):
    """Rows from a retired build (or untagged legacy rows) must not count
    toward this build's certification progress — this is the actual fix
    under test, not just a side effect of the row shape."""
    monkeypatch.chdir(tmp_path)
    rows = [
        {
            "date": "2026-06-15T00:00:00+00:00",
            "ticket": "1",
            "signal": "BUY",
            "lot": 0.01,
            "profit": 10,
            "result": "WIN",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": "SOME-OLDER-BUILD",
        },
        {
            "date": "2026-06-15T00:01:00+00:00",
            "ticket": "2",
            "signal": "BUY",
            "lot": 0.01,
            "profit": -5,
            "result": "LOSS",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": "",
        },
    ]
    dump_rows(HISTORY_FILE, HISTORY_COLUMNS, rows)
    snapshot = update_certification_progress()
    assert snapshot["closed_trade_count"] == 0


def test_certification_separates_bot_from_manual_trades(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [
        {
            "date": "2026-06-15T00:01:00+00:00",
            "ticket": "1",
            "signal": "BUY",
            "lot": 0.01,
            "profit": 10,
            "result": "WIN",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        },
        {
            "date": "2026-06-15T00:02:00+00:00",
            "ticket": "2",
            "signal": "BUY",
            "lot": 0.01,
            "profit": 10,
            "result": "WIN",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        },
        {
            "date": "2026-06-15T00:03:00+00:00",
            "ticket": "3",
            "signal": "BUY",
            "lot": 0.01,
            "profit": 5,
            "result": "WIN",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        },
        {
            "date": "2026-06-15T00:04:00+00:00",
            "ticket": "4",
            "signal": "BUY",
            "lot": 0.01,
            "profit": -5,
            "result": "LOSS",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        },
        {
            "date": "2026-06-15T00:05:00+00:00",
            "ticket": "5",
            "signal": "BUY",
            "lot": 0.01,
            "profit": -5,
            "result": "LOSS",
            "strategy": "SMC",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        },
    ]
    rows += [
        {
            "date": "2026-06-15T00:10:00+00:00",
            "ticket": "100",
            "signal": "SELL",
            "lot": 0.01,
            "profit": -200,
            "result": "LOSS",
            "strategy": "MANUAL",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 1.0,
            "quality_score": 50,
            "brain_score": 50,
            "build_id": BUILD_ID,
        },
        {
            "date": "2026-06-15T00:11:00+00:00",
            "ticket": "101",
            "signal": "BUY",
            "lot": 0.01,
            "profit": 50,
            "result": "WIN",
            "strategy": "MANUAL",
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 1.0,
            "quality_score": 50,
            "brain_score": 50,
            "build_id": BUILD_ID,
        },
    ]
    dump_rows(HISTORY_FILE, HISTORY_COLUMNS, rows)
    snapshot = build_certification_snapshot()

    assert snapshot["bot_trade_count"] == 5
    assert snapshot["manual_trade_count"] == 2
    assert snapshot["closed_trade_count"] == 7
    assert snapshot["bot_metrics"]["net_profit"] == 15
    assert snapshot["account_metrics"]["net_profit"] == -135
    assert snapshot["manual_metrics"]["net_profit"] == -150
    assert snapshot["levels"][0]["progress_trades"] == 5
    assert snapshot["overall_metrics"] == snapshot["account_metrics"]


def test_certification_counts_unlisted_bot_strategies_as_bot_not_manual(tmp_path, monkeypatch):
    """RECOVERY and SURVIVAL (core/risk_manager.py, core/candle_trigger.py,
    core/survival_intelligence.py, ...) are real bot strategies but were
    missing from an older hardcoded allowlist in _is_bot_row, so closing a
    RECOVERY/SURVIVAL trade silently counted it as MANUAL and understated
    certification progress. _is_bot_row must key off MANUAL specifically,
    not a fixed strategy allowlist, so any current or future non-MANUAL
    strategy (spelled here as a made-up 'FUTURE_STRATEGY' to prove it isn't
    special-cased) is counted as a bot trade without editing this file."""
    monkeypatch.chdir(tmp_path)
    rows = [
        {
            "date": f"2026-06-15T00:{i:02d}:00+00:00",
            "ticket": str(i),
            "signal": "BUY",
            "lot": 0.01,
            "profit": 10,
            "result": "WIN",
            "strategy": strategy,
            "session": "LONDON",
            "market_regime": "RANGING",
            "exec_grade": "A",
            "rr_ratio": 2.0,
            "quality_score": 70,
            "brain_score": 70,
            "build_id": BUILD_ID,
        }
        for i, strategy in enumerate(["RECOVERY", "SURVIVAL", "FUTURE_STRATEGY"], start=1)
    ]
    dump_rows(HISTORY_FILE, HISTORY_COLUMNS, rows)
    snapshot = build_certification_snapshot()

    assert snapshot["bot_trade_count"] == 3
    assert snapshot["manual_trade_count"] == 0
    assert snapshot["levels"][0]["progress_trades"] == 3
