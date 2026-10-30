"""Canonical risk policy used across the project.

This module's role is to be the single source of *documented, validated*
risk limits, with core/settings.py remaining the single source of *live*
values -- get_risk_policy() below reads settings directly rather than
keeping its own copy, so the two cannot drift apart.

AUDIT HISTORY [REARCH-3]: this file used to hold a second, hand-maintained
copy of every value in DEFAULT_RISK_POLICY below, and did drift silently
(max_daily_trades: 80 here vs. settings.MAX_DAILY_TRADES=50 -- see
tests/test_governance_p0.py's AUDIT FIX note). That was a structural
problem, not a one-off typo: as long as get_risk_policy() returned a static
dict, agreement with settings.py depended entirely on a human remembering to
edit both files, with only a governance test to catch it after the fact.
get_risk_policy() now reads core.settings directly, so that class of drift
is no longer possible by construction. DEFAULT_RISK_POLICY is kept below as
a documented reference snapshot only (useful for validate_risk_policy()'s
own unit tests without importing core.settings) -- it is not read by
get_risk_policy() and is not live.

core/risk_manager.py (which actually enforces risk limits on every live
trade) still reads core.settings directly rather than importing this module
-- this file documents and validates the policy, it does not execute it.
That is an intentional, narrower scope than earlier drafts of this docstring
implied; making this module the actual enforcement path (replacing
risk_manager.py's settings-reads with policy-reads) is a separate, larger
decision with its own live-behaviour implications and is out of scope for
this pass.
"""

from __future__ import annotations

from typing import Any, Dict


# Reference snapshot only -- NOT read by get_risk_policy() below. Documents
# what the policy is expected to look like and gives validate_risk_policy()
# something to check in isolation, without importing core.settings.
# [FER3ON-2026-08-31] Updated to match actual live values in settings.py
DEFAULT_RISK_POLICY: Dict[str, Any] = {
    "max_daily_loss_usd": 100.0,
    "max_daily_risk_pct": 10.0,
    "max_position_risk_pct": 1.0,
    "max_total_risk_pct": 1.5,
    "max_open_trades": 4,
    "max_daily_trades": 50,
    "max_open_per_strategy": 1,
    "min_effective_risk_pct": 0.75,
    "min_lot": 0.01,
    "max_lot": 0.08,
    "max_sl_distance_dollars": 15.0,  # Updated from 30.0 (2026-08-28 cap)
    "min_lot_risk_multiple_cap": 5.0,  # Updated for small accounts
    "cooldown_after_loss_sec": 300,
    "loss_pause_trigger": 2,
    "loss_pause_require_fresh": True,
    "hard_risk_cap_enabled": True,
    "anti_revenge_loss_trigger": 2,
    "recovery_risk_multiplier": 0.5,
}


def get_risk_policy() -> Dict[str, Any]:
    """Return the canonical risk policy, read live from core.settings.

    Every field is sourced directly from core.settings (or from
    core.settings.RISK_CONFIG, itself a settings-derived dict -- see that
    module's own "Compatibility alias" note) so this function cannot report
    a value that disagrees with what the live path actually enforces.
    """
    from core import settings as _settings

    return {
        "max_daily_loss_usd": _settings.MAX_DAILY_LOSS_USD,
        "max_daily_risk_pct": _settings.MAX_RISK_PER_DAY_PERCENT,
        "max_position_risk_pct": _settings.RISK_PER_TRADE_PERCENT,
        "max_total_risk_pct": _settings.MAX_RISK_TOTAL,
        "max_open_trades": _settings.MAX_OPEN_TRADES,
        "max_daily_trades": _settings.MAX_DAILY_TRADES,
        "max_open_per_strategy": _settings.MAX_OPEN_PER_STRATEGY,
        "min_effective_risk_pct": _settings.MIN_EFFECTIVE_RISK_PERCENT,
        "min_lot": _settings.MIN_LOT,
        "max_lot": _settings.MAX_LOT,
        "max_sl_distance_dollars": _settings.MAX_SL_DISTANCE_DOLLARS,
        "min_lot_risk_multiple_cap": _settings.MIN_LOT_RISK_MULTIPLE_CAP,
        "cooldown_after_loss_sec": _settings.LOSS_PAUSE_COOLDOWN_SEC,
        "loss_pause_trigger": _settings.LOSS_PAUSE_TRIGGER,
        "loss_pause_require_fresh": _settings.LOSS_PAUSE_REQUIRE_FRESH,
        "hard_risk_cap_enabled": bool(_settings.V7_HARD_RISK_CAP_ENABLED),
        "anti_revenge_loss_trigger": _settings.RISK_CONFIG["anti_revenge_loss_trigger"],
        "recovery_risk_multiplier": _settings.RISK_CONFIG["recovery_risk_multiplier"],
    }


def validate_risk_policy(policy: Dict[str, Any]) -> bool:
    """Validate the risk policy structure and sanity bounds."""
    required_keys = {
        "max_daily_risk_pct",
        "max_daily_loss_usd",
        "max_position_risk_pct",
        "max_total_risk_pct",
        "max_open_trades",
        "max_daily_trades",
        "max_open_per_strategy",
        "min_effective_risk_pct",
        "min_lot",
        "max_lot",
        "max_sl_distance_dollars",
        "min_lot_risk_multiple_cap",
        "cooldown_after_loss_sec",
        "loss_pause_trigger",
        "loss_pause_require_fresh",
        "hard_risk_cap_enabled",
        "anti_revenge_loss_trigger",
        "recovery_risk_multiplier",
    }

    missing = sorted(required_keys - set(policy.keys()))
    if missing:
        return False

    checks = [
        ("max_daily_loss_usd", 0.0, 1000000.0),
        ("max_daily_risk_pct", 0.0, 100.0),
        ("max_position_risk_pct", 0.0, 10.0),
        ("max_total_risk_pct", 0.0, 100.0),
        ("max_open_trades", 0, 1000),
        ("max_daily_trades", 0, 10000),
        ("max_open_per_strategy", 0, 100),
        ("min_effective_risk_pct", 0.0, 100.0),
        ("min_lot", 0.0, 10.0),
        ("max_lot", 0.0, 100.0),
        ("max_sl_distance_dollars", 0.0, 10000.0),
        ("min_lot_risk_multiple_cap", 1.0, 1000.0),
        ("cooldown_after_loss_sec", 0, 86400),
        ("loss_pause_trigger", 0, 100),
        ("anti_revenge_loss_trigger", 0, 100),
    ]

    for key, low, high in checks:
        value = policy.get(key)
        if value is None or not isinstance(value, (int, float, bool)):
            return False
        if value < low or value > high:
            return False

    if not isinstance(policy["loss_pause_require_fresh"], bool):
        return False

    if policy["max_lot"] < policy["min_lot"]:
        return False

    if policy["max_position_risk_pct"] > policy["max_total_risk_pct"]:
        return False

    return True
