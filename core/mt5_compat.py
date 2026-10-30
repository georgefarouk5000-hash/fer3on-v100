"""MT5 compatibility shim.
Provides a safe fallback on non-Windows or test environments where
MetaTrader5 package is unavailable.
"""
from __future__ import annotations

from collections import namedtuple


REQUIRED_MT5_API = {
    "initialize",
    "shutdown",
    "account_info",
    "terminal_info",
    "copy_rates_from_pos",
    "symbol_info_tick",
    "symbol_info",
    "positions_get",
    "history_deals_get",
    "order_check",
    "order_send",
}


def _make_stub():
    _Tick = namedtuple("Tick", ["bid", "ask"])
    _SymbolInfo = namedtuple(
        "SymbolInfo",
        ["trade_tick_value", "volume_step", "point", "filling_mode"],
        defaults=(0.10, 0.01, 0.01, 1),
    )
    _AccountInfo = namedtuple(
        "AccountInfo",
        ["trade_mode", "balance", "equity", "profit", "margin", "margin_mode"],
        defaults=(0, 10000.0, 10000.0, 0.0, 0.0, 2),
    )
    _TerminalInfo = namedtuple("TerminalInfo", ["connected"], defaults=(False,))
    _TradeResult = namedtuple("TradeResult", ["retcode", "order"], defaults=(10009, 0))
    _CheckResult = namedtuple("CheckResult", ["retcode", "comment"], defaults=(10009, "stub"))

    class _MT5Stub:
        is_stub = True

        TIMEFRAME_M1 = 1
        TIMEFRAME_M5 = 5
        TIMEFRAME_M15 = 15
        TIMEFRAME_H1 = 60
        TIMEFRAME_H4 = 240
        TIMEFRAME_D1 = 1440
        TIMEFRAME_W1 = 10080

        ACCOUNT_TRADE_MODE_DEMO = 0
        ACCOUNT_TRADE_MODE_CONTEST = 1
        ACCOUNT_TRADE_MODE_REAL = 2

        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        POSITION_TYPE_BUY = 0
        POSITION_TYPE_SELL = 1
        ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

        ORDER_FILLING_FOK = 0
        ORDER_FILLING_IOC = 1
        ORDER_FILLING_RETURN = 2

        ORDER_TIME_GTC = 0
        TRADE_ACTION_DEAL = 1
        TRADE_ACTION_SLTP = 2
        TRADE_RETCODE_DONE = 10009

        def initialize(self, *args, **kwargs):
            return True

        def shutdown(self):
            return True

        def last_error(self):
            return (-1, "MetaTrader5 package not available")

        def account_info(self):
            return _AccountInfo()

        def terminal_info(self):
            return _TerminalInfo(True)

        def copy_rates_from_pos(self, *args, **kwargs):
            return None

        def symbol_info_tick(self, *args, **kwargs):
            return _Tick(0.0, 0.0)

        def symbol_info(self, *args, **kwargs):
            return _SymbolInfo()

        def positions_get(self, *args, **kwargs):
            return []

        def history_deals_get(self, *args, **kwargs):
            return []

        def order_check(self, *args, **kwargs):
            return _CheckResult()

        def order_send(self, *args, **kwargs):
            return _TradeResult()

    return _MT5Stub()


def _module_has_required_api(module) -> bool:
    return module is not None and all(hasattr(module, name) for name in REQUIRED_MT5_API)


def connect_mt5():
    """Return True when MT5 is ready, falling back to stub mode when unavailable."""
    if MT5_AVAILABLE:
        try:
            return bool(mt5.initialize())
        except Exception:
            return False

    return True


try:
    import MetaTrader5 as _real_mt5  # type: ignore
    if _module_has_required_api(_real_mt5):
        mt5 = _real_mt5
        MT5_AVAILABLE = True
    else:
        mt5 = _make_stub()
        MT5_AVAILABLE = False
except Exception:
    mt5 = _make_stub()
    MT5_AVAILABLE = False


def copy_rates_safe(symbol, timeframe, start_pos, count):
    """Safely fetch M5/H1/etc. rates and return None when MT5 is unavailable."""
    if not MT5_AVAILABLE or mt5 is None:
        return None

    try:
        return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
    except Exception:
        return None
