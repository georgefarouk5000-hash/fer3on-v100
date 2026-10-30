from types import SimpleNamespace
from unittest.mock import patch

from core.daily.signal import daily_setup_from_rates
import core.daily_trade_manager as daily_trade_manager
from core.settings import DAILY_MAGIC, SMC_MAGIC
from unittest.mock import patch


def test_daily_signal_uses_closed_daily_and_h4_candles():
    daily_rates = [
        {
            "open": float(close) - 0.5,
            "close": float(close),
            "high": float(close) + 1.0,
            "low": float(close) - 1.0,
        }
        for close in range(1, 51)
    ]
    daily_rates.append(
        {"open": 50.0, "close": 45.0, "high": 51.0, "low": 44.0}
    )
    h4_rates = [
        {"open": 10.0, "close": 14.0, "high": 15.0, "low": 9.0},
        {"open": 14.0, "close": 10.0, "high": 15.0, "low": 9.0},
    ]

    signal, bias = daily_setup_from_rates(daily_rates, h4_rates)

    assert signal == "BUY"
    assert bias == "BUY"


def test_daily_manager_identifies_positions_by_magic():
    assert daily_trade_manager._is_daily_position(SimpleNamespace(magic=DAILY_MAGIC))
    assert not daily_trade_manager._is_daily_position(SimpleNamespace(magic=SMC_MAGIC))


def test_regime_selector_routes_daily_only_above_confidence_threshold():
    import main

    smc_snapshot = {"ready": True, "strategy": "SMC"}
    daily_snapshot = {"ready": True, "strategy": "DAILY"}
    with patch.object(main, "DAILY_RUNTIME_ENABLED", True), \
         patch.object(main, "_build_live_snapshot", return_value=daily_snapshot) as build:
        selected = main._select_strategy_snapshot(
            "XAUUSD",
            smc_snapshot,
            recommended_strategy="DAILY",
            recommendation_confidence=0.7,
        )
        assert selected is daily_snapshot
        build.assert_called_once_with("XAUUSD", strategy="DAILY")

        build.reset_mock()
        selected = main._select_strategy_snapshot(
            "XAUUSD",
            smc_snapshot,
            recommended_strategy="DAILY",
            recommendation_confidence=0.69,
        )
        assert selected is smc_snapshot
        build.assert_not_called()


def test_regime_selector_uses_daily_only_when_primary_signal_is_unavailable():
    import main

    unavailable_smc = {"ready": False, "reason": "NO_DIRECTIONAL_SIGNAL"}
    daily_snapshot = {"ready": True, "strategy": "DAILY"}
    with patch.object(main, "DAILY_RUNTIME_ENABLED", True), \
         patch.object(main, "_build_live_snapshot", return_value=daily_snapshot) as build:
        selected = main._select_strategy_snapshot("XAUUSD", unavailable_smc)

    assert selected is daily_snapshot
    build.assert_called_once_with("XAUUSD", strategy="DAILY")


def test_daily_manager_updates_only_improving_closed_candle_stop():
    position = SimpleNamespace(
        magic=DAILY_MAGIC,
        type=0,
        ticket=123,
        sl=1950.0,
        tp=1980.0,
    )
    mt5_fake = SimpleNamespace(
        TIMEFRAME_D1=1440,
        POSITION_TYPE_BUY=0,
        POSITION_TYPE_SELL=1,
        TRADE_ACTION_SLTP=6,
        TRADE_RETCODE_DONE=10009,
        positions_get=lambda **_kwargs: [position],
        copy_rates_from_pos=lambda *_args: [
            {"high": 1970.0, "low": 1960.0},
            {"high": 1968.0, "low": 1955.0},
            {"high": 1966.0, "low": 1958.0},
        ],
        symbol_info_tick=lambda _symbol: SimpleNamespace(bid=1965.0, ask=1965.2),
        symbol_info=lambda _symbol: SimpleNamespace(
            point=0.01,
            trade_stops_level=10,
            digits=2,
        ),
    )
    mt5_fake.order_send = lambda request: sent_requests.append(request) or SimpleNamespace(
        retcode=mt5_fake.TRADE_RETCODE_DONE
    )
    sent_requests = []

    with patch.object(daily_trade_manager, "MT5_AVAILABLE", True), \
         patch.object(daily_trade_manager, "mt5", mt5_fake), \
         patch.object(daily_trade_manager, "demo_execution_status", return_value=(True, "OK")):
        daily_trade_manager.manage_daily_positions("XAUUSD")

    assert len(sent_requests) == 1
    assert sent_requests[0]["position"] == 123
    assert sent_requests[0]["sl"] == 1955.0
