# =========================================
# FER3ON V6 Recovery+ — HARD RISK CAP SYSTEM
# Prevents account destruction — overrides all strategies
# =========================================

from typing import Any, Dict, Optional

from core.settings import (
    V7_PLUS_ENABLED,
    V7_HARD_RISK_CAP_ENABLED,
    HARD_RISK_MAX_PER_TRADE,
    HARD_RISK_MAX_PER_TRADE_CEILING,
    MAX_DAILY_LOSS_USD,
    SYMBOL,
)

# Module state (reset daily via check function)
_daily_loss_amount: float = 0.0
_daily_start_balance: float = 0.0
_last_reset_day: Optional[str] = None
_emergency_stop: bool = False
_emergency_reason: str = ""


def _reset_daily_if_needed(account_balance: float) -> None:
    global _daily_loss_amount, _daily_start_balance, _last_reset_day, _emergency_stop, _emergency_reason

    from datetime import datetime, timezone
    current_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _last_reset_day != current_day:
        _daily_loss_amount = 0.0
        _daily_start_balance = float(account_balance or 0)
        _last_reset_day = current_day
        if _emergency_stop and _emergency_reason == "DAILY_LOSS_LIMIT":
            _emergency_stop = False
            _emergency_reason = ""
            print("[RECOVERY+] HARD_RISK: Daily reset — emergency stop cleared")


def cap_risk_percent(requested_risk: float) -> float:
    """
    Cap per-trade risk to configured maximum.
    Default max 0.5%, ceiling 1.0%.
    """
    if not V7_PLUS_ENABLED or not V7_HARD_RISK_CAP_ENABLED:
        return float(requested_risk or 0)

    req = float(requested_risk or 0)
    cap = float(HARD_RISK_MAX_PER_TRADE)
    ceiling = float(HARD_RISK_MAX_PER_TRADE_CEILING)
    capped = min(req, cap)
    capped = min(capped, ceiling)
    if capped > 0.50:
        capped = 0.50

    if capped < req:
        print(
            f"[RECOVERY+] HARD_RISK: Per-trade cap"
            f" | requested={req:.3f}%"
            f" | capped={capped:.3f}%"
        )
    return round(capped, 4)


def record_trade_loss(profit: float) -> None:
    """Update daily loss tracker (call from trade result handler)."""
    global _daily_loss_amount, _emergency_stop, _emergency_reason

    if profit >= 0:
        return

    _daily_loss_amount += abs(float(profit))
    print(
        f"[RECOVERY+] HARD_RISK: Daily loss updated"
        f" | total={_daily_loss_amount:.2f}"
    )


def set_emergency_stop(reason: str = "MANUAL") -> None:
    """Manually trigger emergency stop."""
    global _emergency_stop, _emergency_reason
    _emergency_stop = True
    _emergency_reason = reason
    print(f"[RECOVERY+] HARD_RISK: EMERGENCY_STOP | reason={reason}")


def clear_emergency_stop() -> None:
    """Clear emergency stop (manual override only)."""
    global _emergency_stop, _emergency_reason
    _emergency_stop = False
    _emergency_reason = ""
    print("[RECOVERY+] HARD_RISK: Emergency stop cleared manually")


def check_hard_risk_cap(
    account_balance: float,
    requested_risk_percent: float = 0.0,
    daily_loss_amount: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluate hard risk cap status.

    Returns HARD_RISK_STATUS:
      ACTIVE          — trading allowed
      LIMIT_REACHED   — per-trade risk capped (still may trade at reduced size)
      EMERGENCY_STOP  — all new trades blocked
    """
    global _daily_loss_amount, _emergency_stop, _emergency_reason

    if not V7_PLUS_ENABLED or not V7_HARD_RISK_CAP_ENABLED:
        return {
            "enabled": False,
            "status": "ACTIVE",
            "hard_risk_status": "ACTIVE",
            "allowed": True,
            "capped_risk_percent": float(requested_risk_percent or 0),
            "daily_loss": 0.0,
            "daily_loss_limit": 0.0,
            "reason": "DISABLED",
        }

    balance = float(account_balance or 0)
    _reset_daily_if_needed(balance)

    daily_limit = float(MAX_DAILY_LOSS_USD)
    if daily_loss_amount is None:
        try:
            from core.daily_loss_guard import get_daily_loss_status
            daily_loss_amount = get_daily_loss_status(symbol=SYMBOL)["daily_loss"]
        except Exception as exc:
            return {
                "enabled": True,
                "status": "EMERGENCY_STOP",
                "hard_risk_status": "EMERGENCY_STOP",
                "allowed": False,
                "capped_risk_percent": 0.0,
                "daily_loss": 0.0,
                "daily_loss_limit": daily_limit,
                "reason": f"DAILY_PNL_UNAVAILABLE:{type(exc).__name__}",
            }
    _daily_loss_amount = float(daily_loss_amount)
    req_risk = float(requested_risk_percent or 0)
    capped_risk = cap_risk_percent(req_risk)

    if _emergency_stop:
        print(
            f"[RECOVERY+] HARD_RISK: EMERGENCY_STOP"
            f" | reason={_emergency_reason}"
        )
        return {
            "enabled": True,
            "status": "EMERGENCY_STOP",
            "hard_risk_status": "EMERGENCY_STOP",
            "allowed": False,
            "capped_risk_percent": 0.0,
            "daily_loss": round(_daily_loss_amount, 2),
            "daily_loss_limit": round(daily_limit, 2),
            "reason": _emergency_reason or "EMERGENCY_STOP",
        }

    if _daily_loss_amount >= daily_limit and daily_limit > 0:
        _emergency_stop = True
        _emergency_reason = "DAILY_LOSS_LIMIT"
        print(
            f"[RECOVERY+] HARD_RISK: EMERGENCY_STOP"
            f" | daily_loss={_daily_loss_amount:.2f}"
            f" | limit={daily_limit:.2f}"
        )
        return {
            "enabled": True,
            "status": "EMERGENCY_STOP",
            "hard_risk_status": "EMERGENCY_STOP",
            "allowed": False,
            "capped_risk_percent": 0.0,
            "daily_loss": round(_daily_loss_amount, 2),
            "daily_loss_limit": round(daily_limit, 2),
            "reason": "DAILY_LOSS_LIMIT",
        }

    status = "ACTIVE"
    if capped_risk < req_risk:
        status = "LIMIT_REACHED"

    print(
        f"[RECOVERY+] HARD_RISK: {status}"
        f" | risk={capped_risk:.3f}%"
        f" | daily_loss={_daily_loss_amount:.2f}/{daily_limit:.2f}"
    )

    return {
        "enabled": True,
        "status": status,
        "hard_risk_status": status,
        "allowed": True,
        "capped_risk_percent": capped_risk,
        "daily_loss": round(_daily_loss_amount, 2),
        "daily_loss_limit": round(daily_limit, 2),
        "reason": status,
    }


def is_trading_blocked(account_balance: float) -> bool:
    """Quick check — True if emergency stop active."""
    result = check_hard_risk_cap(account_balance)
    return not result.get("allowed", True)


def get_hard_risk_status(account_balance: float) -> str:
    """Return HARD_RISK_STATUS string."""
    return check_hard_risk_cap(account_balance).get("hard_risk_status", "ACTIVE")
