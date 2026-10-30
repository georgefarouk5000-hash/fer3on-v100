"""
Regression test for a restart reconciliation bug where positions already
open at the broker were not restored into the in-memory strategy limits.

Root cause: core.portfolio_risk_authority's _STATE.open_trades is in-memory
only. reconcile_with_live_positions() used to be prune-only -- it removed
stale entries but never re-imported a live MT5 position that was already
open when the process started. So every restart reset the per-strategy
open count to 0 regardless of what was actually still open on the broker,
letting a brand new position open on top of one still live from a previous
session.

Fix: reconcile_with_live_positions() now also imports any live position
missing from open_trades, inferring strategy from its magic number.
"""
from unittest.mock import MagicMock

import core.portfolio_risk_authority as pra


def _fake_position(ticket, magic, volume=0.02, price_open=4090.0, sl=4080.0, tp=4110.0, type_=0):
    p = MagicMock()
    p.ticket = ticket
    p.magic = magic
    p.volume = volume
    p.price_open = price_open
    p.sl = sl
    p.tp = tp
    p.type = type_  # 0 = BUY, 1 = SELL
    return p


def test_reconcile_imports_live_position_missing_after_restart(monkeypatch):
    """Simulate a restart with an SMC position already open at the broker."""
    pra.__test_reset__()
    monkeypatch.setattr(
        pra, "get_daily_loss_status",
        lambda **_kwargs: {"daily_pnl": 0.0, "daily_loss": 0.0},
    )
    pra.reset_portfolio_state(balance=1000.0)

    assert len(pra._STATE.open_trades) == 0  # simulating a fresh restart

    live_position = _fake_position(ticket=4242, magic=4001)  # SMC magic
    result = pra.reconcile_with_live_positions([live_position])

    assert result["imported"] == 1
    assert result["removed"] == 0
    assert len(pra._STATE.open_trades) == 1
    assert pra._STATE.open_trades[0]["strategy"] == "SMC"
    assert pra._STATE.open_trades[0]["ticket"] == 4242

    # A second SMC trade must remain blocked after restart reconciliation.
    decision = pra.evaluate_risk(strategy="SMC", direction="BUY", requested_risk_percent=1.0)
    assert not decision.approved
    assert decision.rejection_reason == "PER_STRATEGY_MAX_OPEN_HIT"

    pra.__test_reset__()


def test_reconcile_still_prunes_stale_entries(monkeypatch):
    """Existing behavior must be preserved: an open_trades entry for a
    position that's no longer open on the broker gets removed."""
    pra.__test_reset__()
    monkeypatch.setattr(
        pra, "get_daily_loss_status",
        lambda **_kwargs: {"daily_pnl": 0.0, "daily_loss": 0.0},
    )
    pra.reset_portfolio_state(balance=1000.0)

    pra.record_trade_open(
        ticket=111, strategy="MICRO", direction="BUY", lot=0.01,
        risk_percent=1.0, entry_price=4000.0, sl=3990.0, tp=4010.0,
    )
    assert len(pra._STATE.open_trades) == 1

    result = pra.reconcile_with_live_positions([])  # nothing open on broker now
    assert result["removed"] == 1
    assert result["imported"] == 0
    assert len(pra._STATE.open_trades) == 0

    pra.__test_reset__()


def test_reconcile_does_not_duplicate_already_tracked_position(monkeypatch):
    pra.__test_reset__()
    monkeypatch.setattr(
        pra, "get_daily_loss_status",
        lambda **_kwargs: {"daily_pnl": 0.0, "daily_loss": 0.0},
    )
    pra.reset_portfolio_state(balance=1000.0)

    pra.record_trade_open(
        ticket=222, strategy="SMC", direction="SELL", lot=0.02,
        risk_percent=1.5, entry_price=4090.0, sl=4100.0, tp=4070.0,
    )

    live_position = _fake_position(ticket=222, magic=4001)
    result = pra.reconcile_with_live_positions([live_position])

    assert result["imported"] == 0
    assert len(pra._STATE.open_trades) == 1

    pra.__test_reset__()
