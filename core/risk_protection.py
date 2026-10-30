# =========================================
# FER3ON V5 — RISK PROTECTION
# Delegated wrappers to the unified risk engine
# =========================================

from core.adaptive_ai import market_is_safe as adaptive_market_is_safe
from core.risk_manager import (
    check_drawdown_limits,
    cooldown_active as unified_cooldown_active,
    get_risk_state,
    record_trade_result,
)

# Backward-compatible state mirrors
last_trade_time = 0
consecutive_losses = 0
daily_loss = 0
last_reset_day = None
daily_start_balance = 0

MAX_CONSECUTIVE_LOSSES = 5
MAX_DAILY_LOSS_PERCENT = 3
REVENGE_TRIGGER_LOSSES = 2
RECOVERY_RISK_MULT = 0.50


def _sync_state():
    global last_trade_time, consecutive_losses, daily_loss
    state = get_risk_state()
    last_trade_time = state.get("last_loss_time", 0)
    consecutive_losses = state.get("consecutive_losses", 0)
    daily_loss = state.get("daily_loss_total", 0)
    return state


def reset_daily_state():
    return _sync_state()


def _check_anti_revenge():
    state = _sync_state()
    return state.get("consecutive_losses", 0) >= REVENGE_TRIGGER_LOSSES


def is_recovery_mode():
    active = _check_anti_revenge()
    mult = RECOVERY_RISK_MULT if active else 1.0
    return active, mult


def cooldown_active():
    _sync_state()
    return unified_cooldown_active()


def market_is_safe():
    return adaptive_market_is_safe()


def update_trade_result(profit):
    state = record_trade_result(profit)
    _sync_state()
    return state


def risk_limits_hit(account_balance):
    state = _sync_state()
    status = check_drawdown_limits(balance=account_balance)
    if state.get("consecutive_losses", 0) >= MAX_CONSECUTIVE_LOSSES:
        return True
    return not status.get("allowed", True)
