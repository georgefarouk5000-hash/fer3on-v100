"""
[FER3ON-FIX-2026-08-21] Tests that a crash inside the kill-switch check
blocks the trade (fail-closed) instead of silently allowing it
(the old "non-fatal, allowing trade" behavior).
"""

import pytest

import core.strategy_kill_switch as kill_switch
import core.trade_event_ledger as trade_event_ledger
import core.trade_executor as trade_executor


def _isolate_trade_event_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(
        trade_event_ledger,
        "TRADE_EVENTS_FILE",
        str(tmp_path / "trade_events.jsonl"),
    )


def _boom(**kwargs):
    raise RuntimeError("simulated kill-switch failure")


def test_kill_switch_exception_blocks_the_trade(monkeypatch, tmp_path):
    _isolate_trade_event_ledger(monkeypatch, tmp_path)
    monkeypatch.setattr(kill_switch, "should_block_trade", _boom)

    result = trade_executor.execute_trade(
        request={"action": "TRADE", "symbol": "XAUUSD"},
        strategy="SMC",
        signal="BUY",
        lot=0.01,
        sl_dist=10.0,
        tp_dist=20.0,
        rr_ratio=2.0,
        risk_percent=1.0,
        exec_grade="B",
        final_brain=50.0,
        quality_score=50.0,
        confidence=50.0,
        market_regime="RANGING",
        atr=5.0,
        session="LONDON",
        magic=1001,
    )

    assert result.get("retcode") == -1, (
        "an exception in the safety check must block the trade — "
        "the old behavior returned nothing here and fell through to order_send"
    )
    assert "FAIL_CLOSED" in str(result.get("comment", ""))


def test_kill_switch_normal_block_is_unaffected(monkeypatch, tmp_path):
    _isolate_trade_event_ledger(monkeypatch, tmp_path)
    """تأكيد إن الإصلاح ملموش على المسار العادي (block=True صريح، بدون
    استثناء) — لازم يفضل يرجع نفس الشكل زي الأول."""
    monkeypatch.setattr(
        kill_switch, "should_block_trade",
        lambda **kwargs: (True, "KILL_SWITCH_DAILY_LOSS_SMC_test"),
    )

    result = trade_executor.execute_trade(
        request={"action": "TRADE", "symbol": "XAUUSD"},
        strategy="SMC",
        signal="BUY",
        lot=0.01,
        sl_dist=10.0,
        tp_dist=20.0,
        rr_ratio=2.0,
        risk_percent=1.0,
        exec_grade="B",
        final_brain=50.0,
        quality_score=50.0,
        confidence=50.0,
        market_regime="RANGING",
        atr=5.0,
        session="LONDON",
        magic=1001,
    )

    assert result.get("retcode") == -1
    assert result.get("comment") == "KILL_SWITCH_DAILY_LOSS_SMC_test"
