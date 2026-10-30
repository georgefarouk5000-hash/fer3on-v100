"""Compatibility shim for legacy imports.

The project must always use core.settings as the single source of truth for risk
limits. This module mirrors those values instead of defining independent risk
configuration.
"""

from __future__ import annotations

import sys


def _canonical_risk_config():
    if "core.settings" not in sys.modules:
        return {}

    settings = sys.modules["core.settings"]
    return {
        "max_daily_risk": getattr(settings, "MAX_DAILY_RISK", 0.0),
        "max_daily_risk_pct": getattr(settings, "MAX_RISK_PER_DAY_PERCENT", 0.0),
        "max_risk_per_trade_pct": getattr(settings, "RISK_PER_TRADE_PERCENT", 0.0),
        "max_open_trades": getattr(settings, "MAX_OPEN_TRADES", 0),
        "max_day_loss_pct": getattr(settings, "MAX_RISK_PER_DAY_PERCENT", 0.0),
        "max_position_risk": getattr(settings, "RISK_PER_TRADE_PERCENT", 0.0),
        "max_drawdown": 0.08,
        "recovery_risk_multiplier": 0.5,
        "anti_revenge_loss_trigger": 2,
        "cooldown_after_loss": 300,
        "hard_stop_enabled": True,
        "survival_mode_enabled": True,
    }


RISK_CONFIG = _canonical_risk_config()


def get_risk_config():
    return dict(_canonical_risk_config())
