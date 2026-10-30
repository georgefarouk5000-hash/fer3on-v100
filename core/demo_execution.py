"""Fail-closed guard for explicitly enabled demo-account order execution."""
from __future__ import annotations

from core.mt5_compat import MT5_AVAILABLE, mt5


def demo_execution_status(*, mt5_module=None, mt5_available=None) -> tuple[bool, str]:
    """Return whether order sends are explicitly enabled on a verified demo account."""
    from core.settings import DEMO_TRADING_ENABLED, SHADOW_ONLY_RUNTIME

    if not DEMO_TRADING_ENABLED:
        return False, "DEMO_TRADING_NOT_ENABLED"
    if SHADOW_ONLY_RUNTIME:
        return False, "SHADOW_ONLY_RUNTIME"

    module = mt5 if mt5_module is None else mt5_module
    available = MT5_AVAILABLE if mt5_available is None else mt5_available
    if not available or module is None:
        return False, "MT5_UNAVAILABLE"

    demo_mode = getattr(module, "ACCOUNT_TRADE_MODE_DEMO", None)
    if demo_mode is None:
        return False, "DEMO_ACCOUNT_MODE_UNVERIFIABLE"

    try:
        account = module.account_info()
        actual_mode = getattr(account, "trade_mode", None) if account is not None else None
        if actual_mode is None or int(actual_mode) != int(demo_mode):
            return False, "MT5_ACCOUNT_IS_NOT_VERIFIED_DEMO"
    except Exception:
        return False, "MT5_ACCOUNT_MODE_CHECK_FAILED"

    return True, "VERIFIED_DEMO"
