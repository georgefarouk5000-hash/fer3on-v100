from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import core.daily_loss_guard as daily_loss_guard
from core.daily_loss_guard import get_daily_loss_status


class FakeMT5:
    def __init__(self, deals, positions=()):
        self.deals = deals
        self.positions = positions
        self.requested_range = None
        self.history_calls = 0
        self.positions_calls = 0

    def history_deals_get(self, start, end):
        self.history_calls += 1
        self.requested_range = (start, end)
        return self.deals

    def positions_get(self, *, symbol):
        self.positions_calls += 1
        return self.positions


def _deal(ticket, pnl, time_msc, symbol="XAUUSD", commission=0.0):
    return SimpleNamespace(
        ticket=ticket,
        symbol=symbol,
        profit=pnl,
        commission=commission,
        swap=0.0,
        fee=0.0,
        time_msc=time_msc,
        time=time_msc // 1000,
    )


def test_daily_loss_tracks_intraday_low_even_after_recovery():
    client = FakeMT5([
        _deal(1, -130.0, 1000),
        _deal(2, 50.0, 2000),
        _deal(3, -999.0, 3000, symbol="EURUSD"),
    ])
    now = datetime(2026, 10, 30, 7, tzinfo=timezone.utc)

    result = get_daily_loss_status(now=now, mt5_client=client)

    assert result == {
        "realized_pnl": -80.0,
        "floating_pnl": 0.0,
        "daily_pnl": -80.0,
        "daily_loss": 130.0,
    }
    assert client.requested_range[0] == datetime(2026, 10, 30, tzinfo=timezone.utc)
    assert client.requested_range[1] == now


def test_daily_loss_includes_costs_and_open_position_floating_pnl():
    client = FakeMT5(
        [_deal(1, -70.0, 1000, commission=-2.0)],
        [SimpleNamespace(profit=-25.0, swap=-3.0)],
    )

    result = get_daily_loss_status(
        now=datetime(2026, 10, 30, 7, tzinfo=timezone.utc),
        mt5_client=client,
    )

    assert result["daily_pnl"] == -100.0
    assert result["daily_loss"] == 100.0


def test_daily_loss_fails_closed_after_retrying_unavailable_mt5_history(monkeypatch):
    monkeypatch.setattr(daily_loss_guard.time_module, "sleep", lambda _delay: None)
    client = FakeMT5(None)

    with pytest.raises(RuntimeError, match="MT5_DEAL_HISTORY_UNAVAILABLE"):
        get_daily_loss_status(
            now=datetime(2026, 10, 30, 7, tzinfo=timezone.utc),
            mt5_client=client,
        )

    assert client.history_calls == daily_loss_guard.MT5_READ_ATTEMPTS
    assert client.positions_calls == 0


def test_daily_loss_retries_transient_mt5_failure_then_returns_current_data(monkeypatch):
    monkeypatch.setattr(daily_loss_guard.time_module, "sleep", lambda _delay: None)

    class TransientMT5(FakeMT5):
        def history_deals_get(self, start, end):
            self.history_calls += 1
            self.requested_range = (start, end)
            return None if self.history_calls == 1 else []

    client = TransientMT5([])

    result = get_daily_loss_status(
        now=datetime(2026, 10, 30, 7, tzinfo=timezone.utc),
        mt5_client=client,
    )

    assert result["daily_loss"] == 0.0
    assert client.history_calls == 2
    assert client.positions_calls == 1


def test_daily_loss_retries_when_mt5_positions_are_unavailable(monkeypatch):
    monkeypatch.setattr(daily_loss_guard.time_module, "sleep", lambda _delay: None)
    client = FakeMT5([], positions=None)

    with pytest.raises(RuntimeError, match="MT5_POSITION_STATE_UNAVAILABLE"):
        get_daily_loss_status(
            now=datetime(2026, 10, 30, 7, tzinfo=timezone.utc),
            mt5_client=client,
        )

    assert client.history_calls == daily_loss_guard.MT5_READ_ATTEMPTS
    assert client.positions_calls == daily_loss_guard.MT5_READ_ATTEMPTS


def test_daily_loss_rejects_naive_clock():
    with pytest.raises(ValueError, match="timezone-aware"):
        get_daily_loss_status(
            now=datetime(2026, 10, 30, 7),
            mt5_client=FakeMT5([]),
        )
