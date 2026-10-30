# =============================================================================
# FER3ON V3+++ — PHASE 2 | PERFORMANCE REPOSITORY
# =============================================================================
# Unified read-only interface for all Phase-2 analytics modules.
# Every Phase-2 module MUST read through here — never directly from
# Truth Layer internals or runtime files.
#
# SAFETY CONTRACT:
#   ✅ Reads only from analytics.truth_layer
#   ✅ No writes to any live runtime file
#   ✅ No imports from core runtime modules (main, risk, adaptive, etc.)
#   ✅ PHASE2_RUNTIME_INFLUENCE is always False — asserted at import
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from analytics.truth_layer import (
    TradeRecord,
    Metrics,
    load_all_trades,
    filter_trades,
    compute_metrics,
    breakdown_by_strategy,
    breakdown_by_session,
    breakdown_by_regime,
)
from core.settings import PHASE2_RUNTIME_INFLUENCE, BUILD_ID

# Hard guard: if someone accidentally sets this True, blow up early.
assert not PHASE2_RUNTIME_INFLUENCE, (
    "PHASE2_RUNTIME_INFLUENCE must be False. "
    "Phase-2 is analytics-only and must never influence live trading."
)


# =============================================================================
# PUBLIC API
# =============================================================================

def get_all_trades() -> List[TradeRecord]:
    """Return only current-build trades for active analytics consumers."""
    return filter_trades(load_all_trades(), build_id=BUILD_ID)


def get_all_trades_including_legacy() -> List[TradeRecord]:
    """Return the complete archive explicitly for historical audit reports."""
    return load_all_trades()


def get_overall_metrics(trades: Optional[List[TradeRecord]] = None) -> Metrics:
    """Overall portfolio metrics across all trades."""
    if trades is None:
        trades = get_all_trades()
    return compute_metrics(trades)


def get_session_breakdown(
    trades: Optional[List[TradeRecord]] = None,
) -> Dict[str, Metrics]:
    """Per-session metrics keyed by session name (upper-case)."""
    if trades is None:
        trades = get_all_trades()
    return breakdown_by_session(trades)


def get_regime_breakdown(
    trades: Optional[List[TradeRecord]] = None,
) -> Dict[str, Metrics]:
    """Per-regime metrics keyed by regime name (upper-case)."""
    if trades is None:
        trades = get_all_trades()
    return breakdown_by_regime(trades)


def get_strategy_breakdown(
    trades: Optional[List[TradeRecord]] = None,
) -> Dict[str, Metrics]:
    """Per-strategy metrics keyed by strategy name (upper-case)."""
    if trades is None:
        trades = get_all_trades()
    return breakdown_by_strategy(trades)


def get_trades_for_session(
    session: str,
    trades: Optional[List[TradeRecord]] = None,
) -> List[TradeRecord]:
    if trades is None:
        trades = get_all_trades()
    return filter_trades(trades, session=session)


def get_trades_for_regime(
    regime: str,
    trades: Optional[List[TradeRecord]] = None,
) -> List[TradeRecord]:
    if trades is None:
        trades = get_all_trades()
    return filter_trades(trades, regime=regime)


def get_trades_for_strategy(
    strategy: str,
    trades: Optional[List[TradeRecord]] = None,
) -> List[TradeRecord]:
    if trades is None:
        trades = get_all_trades()
    return filter_trades(trades, strategy=strategy)


def get_trades_in_range(
    since: str,
    until: str,
    trades: Optional[List[TradeRecord]] = None,
) -> List[TradeRecord]:
    """ISO-8601 datetime strings for since/until (inclusive)."""
    if trades is None:
        trades = load_all_trades()
    return filter_trades(trades, since=since, until=until)


# =============================================================================
# HELPER UTILITIES — safe for Phase-2 internal use only
# =============================================================================

def group_trades_by(
    trades: List[TradeRecord],
    field_name: str,
) -> Dict[str, List[TradeRecord]]:
    """Group trades by any TradeRecord field value."""
    from collections import defaultdict
    out: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in trades:
        value = str(getattr(t, field_name, "UNKNOWN") or "UNKNOWN").upper()
        out[value].append(t)
    return dict(out)


def safe_metrics_dict(metrics: Metrics) -> Dict[str, Any]:
    """Convert Metrics to JSON-safe dict, replacing infinity."""
    d = metrics.to_dict()
    for k, v in d.items():
        if isinstance(v, float) and (v == float("inf") or v != v):  # inf or NaN
            d[k] = None
    return d


def describe_metrics(metrics: Metrics, label: str = "") -> str:
    """Human-readable one-liner summary."""
    pf = f"{metrics.profit_factor:.2f}" if metrics.profit_factor != float("inf") else "∞"
    return (
        f"{label + ' | ' if label else ''}"
        f"Trades={metrics.total_trades}  "
        f"WR={metrics.win_rate:.1%}  "
        f"PF={pf}  "
        f"Exp={metrics.expectancy:.2f}  "
        f"MaxDD={metrics.max_drawdown:.2f}"
    )
