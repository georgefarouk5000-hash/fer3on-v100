"""Single coordination facade for open-position management.

This module owns the order of advisory management operations. The existing
trailing and TP implementations remain behind this facade for compatibility;
callers should use manage_open_positions instead of invoking them separately.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def manage_open_positions(
    symbol: str,
    atr: float = 0.0,
    *,
    mt5_available: Optional[bool] = None,
) -> Dict[str, Any]:
    """Run trailing and TP monitoring in one deterministic cycle.

    Both underlying components retain their existing advisory/live settings.
    This coordinator does not change those settings and never sends an order
    itself.
    """
    result: Dict[str, Any] = {
        "ok": True,
        "trailing_ran": False,
        "tp_monitor_ran": False,
        "errors": [],
    }
    try:
        from core.mt5_compat import MT5_AVAILABLE
        available = MT5_AVAILABLE if mt5_available is None else bool(mt5_available)
        if not available:
            return result

        from core.trailing_stop import update_position_trailing
        update_position_trailing(symbol, atr)
        result["trailing_ran"] = True
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"TRAILING:{type(exc).__name__}")

    try:
        from core.mt5_compat import MT5_AVAILABLE
        available = MT5_AVAILABLE if mt5_available is None else bool(mt5_available)
        if not available:
            return result

        from execution.tp_monitor import process_tp_ladders
        process_tp_ladders(symbol)
        result["tp_monitor_ran"] = True
    except Exception as exc:
        result["ok"] = False
        result["errors"].append(f"TP_MONITOR:{type(exc).__name__}")

    return result
