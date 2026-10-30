from types import SimpleNamespace

import core.settings as settings
import core.demo_execution as demo_execution
from core.demo_execution import demo_execution_status


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self, trade_mode):
        self._trade_mode = trade_mode

    def account_info(self):
        return SimpleNamespace(trade_mode=self._trade_mode)


def test_demo_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_TRADING_ENABLED", False)
    monkeypatch.setattr(settings, "SHADOW_ONLY_RUNTIME", False)

    assert demo_execution_status(
        mt5_module=FakeMT5(0), mt5_available=True
    ) == (False, "DEMO_TRADING_NOT_ENABLED")


def test_shadow_mode_blocks_demo_orders(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "SHADOW_ONLY_RUNTIME", True)

    assert demo_execution_status(
        mt5_module=FakeMT5(0), mt5_available=True
    ) == (False, "SHADOW_ONLY_RUNTIME")


def test_enabled_demo_orders_require_verified_demo_account(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "SHADOW_ONLY_RUNTIME", False)

    assert demo_execution_status(
        mt5_module=FakeMT5(0), mt5_available=True
    ) == (True, "VERIFIED_DEMO")
    assert demo_execution_status(
        mt5_module=FakeMT5(2), mt5_available=True
    ) == (False, "MT5_ACCOUNT_IS_NOT_VERIFIED_DEMO")


def test_unavailable_or_unverifiable_account_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_TRADING_ENABLED", True)
    monkeypatch.setattr(settings, "SHADOW_ONLY_RUNTIME", False)

    assert demo_execution_status(mt5_module=FakeMT5(0), mt5_available=False) == (
        False,
        "MT5_UNAVAILABLE",
    )
    assert demo_execution_status(
        mt5_module=SimpleNamespace(account_info=lambda: None),
        mt5_available=True,
    ) == (False, "DEMO_ACCOUNT_MODE_UNVERIFIABLE")


def test_trade_executor_blocks_order_when_demo_guard_denies(monkeypatch, tmp_path):
    import core.loss_pause_guard as loss_pause_guard
    import core.strategy_kill_switch as strategy_kill_switch
    import core.trade_event_ledger as trade_event_ledger
    import core.trade_executor as trade_executor

    monkeypatch.setattr(
        trade_event_ledger,
        "TRADE_EVENTS_FILE",
        str(tmp_path / "trade_events.jsonl"),
    )
    monkeypatch.setattr(
        loss_pause_guard,
        "evaluate_loss_pause",
        lambda *args, **kwargs: {"trading_allowed": True, "consecutive_losses": 0},
    )
    monkeypatch.setattr(
        strategy_kill_switch,
        "should_block_trade",
        lambda **kwargs: (False, "OK"),
    )
    monkeypatch.setattr(
        demo_execution,
        "demo_execution_status",
        lambda: (False, "MT5_ACCOUNT_IS_NOT_VERIFIED_DEMO"),
    )

    result = trade_executor.execute_trade(
        request={"action": "TRADE", "symbol": "XAUUSD", "volume": 0.01},
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

    assert result == {
        "retcode": -20,
        "comment": "MT5_ACCOUNT_IS_NOT_VERIFIED_DEMO",
    }
