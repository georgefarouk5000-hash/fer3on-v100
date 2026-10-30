# =============================================================================
# FER3ON AI V3.5 — SETUP ANALYZER
# =============================================================================
# Answers: "Which setup actually wins?"
# Instead of: "Did the bot profit today?"
#
# For each strategy:
#   - Win Rate
#   - Profit Factor
#   - Expectancy
#   - Average RR
#   - Average Hold Time
#   - Session Performance
#   - Regime Performance
#
# Builds on top of analytics.truth_layer so all math is centralized.
# =============================================================================

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from analytics.truth_layer import (
    TradeRecord,
    compute_metrics,
    filter_trades,
    load_all_trades,
    Metrics,
)


STRATEGIES: Tuple[str, ...] = ("SMC", "DAILY")


def _metric_group_to_dict(metrics: Metrics) -> Dict[str, Any]:
    return {
        "metrics": metrics.to_dict(),
        "samples_sufficient": metrics.total_trades >= 5,
        "verdict": _verdict(metrics, _setup_score(metrics)),
    }


# =============================================================================
# SETUP ANALYSIS (per strategy)
# =============================================================================

@dataclass
class SetupAnalysis:
    strategy: str
    metrics: Metrics
    session_breakdown: Dict[str, Metrics]
    regime_breakdown: Dict[str, Metrics]
    entry_reason_breakdown: Dict[str, Metrics]
    entry_condition_breakdown: Dict[str, Metrics]
    setup_score: float
    rank: int = 0
    verdict: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "metrics": self.metrics.to_dict(),
            "session_breakdown": {k: v.to_dict() for k, v in self.session_breakdown.items()},
            "regime_breakdown":  {k: v.to_dict() for k, v in self.regime_breakdown.items()},
            "entry_reason_breakdown": {
                k: _metric_group_to_dict(v) for k, v in self.entry_reason_breakdown.items()
            },
            "entry_condition_breakdown": {
                k: _metric_group_to_dict(v) for k, v in self.entry_condition_breakdown.items()
            },
            "setup_score": round(self.setup_score, 2),
            "rank": self.rank,
            "verdict": self.verdict,
        }


def persist_setup_analysis_report(
    *,
    report_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist the existing setup analysis for the runtime and dashboards."""
    from core.settings import SETUP_ANALYSIS_REPORT_PATH

    path = report_path or SETUP_ANALYSIS_REPORT_PATH
    report = overall_setups_report()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)
    return report


def _setup_score(m: Metrics) -> float:
    """Composite scoring used to rank setups.
    Higher = better setup quality.
    """
    if m.total_trades == 0:
        return 0.0
    pf = m.profit_factor if m.profit_factor != float("inf") else 5.0
    pf = min(max(pf, 0.0), 5.0)  # cap at 5
    score = (
        m.win_rate * 40.0
        + (pf / 5.0) * 30.0
        + (m.expectancy / max(1.0, abs(m.expectancy) + 1.0)) * 10.0
        + (1.0 - min(m.max_drawdown / 1000.0, 1.0)) * 10.0
        + min(m.total_trades / 50.0, 1.0) * 10.0
    )
    return round(score, 2)


def _verdict(m: Metrics, score: float) -> str:
    if m.total_trades < 5:
        return "INSUFFICIENT_SAMPLES"
    if m.profit_factor >= 1.5 and m.win_rate >= 0.55:
        return "PROFITABLE"
    if m.profit_factor >= 1.0 and m.expectancy > 0:
        return "EDGE_PRESENT"
    if m.profit_factor < 0.85 or m.expectancy < 0:
        return "WEAK_NEGATIVE_EDGE"
    return "MIXED"


def analyze_setup(
    strategy: str,
    trades: Optional[List[TradeRecord]] = None,
) -> SetupAnalysis:
    """Compute full breakdown for a single strategy."""
    strat = strategy.upper()
    if trades is None:
        trades = load_all_trades()
    own = [t for t in trades if t.strategy.upper() == strat]
    metrics = compute_metrics(own)
    sessions: Dict[str, List[TradeRecord]] = defaultdict(list)
    regimes:  Dict[str, List[TradeRecord]] = defaultdict(list)
    reasons: Dict[str, List[TradeRecord]] = defaultdict(list)
    conditions: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in own:
        sessions[(t.session or "UNKNOWN").upper()].append(t)
        regimes[(t.regime  or "UNKNOWN").upper()].append(t)
        reasons[(t.entry_reason or "UNKNOWN").strip().upper()].append(t)
        raw_conditions = t.entry_conditions or []
        if isinstance(raw_conditions, str):
            try:
                parsed_conditions = json.loads(raw_conditions)
            except (TypeError, ValueError):
                parsed_conditions = [raw_conditions]
            raw_conditions = (
                parsed_conditions if isinstance(parsed_conditions, list) else []
            )
        seen_conditions = set()
        for condition in raw_conditions:
            key = str(condition or "").strip().upper()
            if key and key not in seen_conditions:
                conditions[key].append(t)
                seen_conditions.add(key)
    s_metrics = {k: compute_metrics(v) for k, v in sessions.items()}
    r_metrics = {k: compute_metrics(v) for k, v in regimes.items()}
    reason_metrics = {k: compute_metrics(v) for k, v in reasons.items()}
    condition_metrics = {k: compute_metrics(v) for k, v in conditions.items()}
    return SetupAnalysis(
        strategy=strat,
        metrics=metrics,
        session_breakdown=s_metrics,
        regime_breakdown=r_metrics,
        entry_reason_breakdown=reason_metrics,
        entry_condition_breakdown=condition_metrics,
        setup_score=_setup_score(metrics),
        verdict=_verdict(metrics, _setup_score(metrics)),
    )


def analyze_all_setups(
    trades: Optional[List[TradeRecord]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Dict[str, SetupAnalysis]:
    """Analyze every registered strategy. Ranked output."""
    if trades is None:
        trades = load_all_trades()
    if since or until:
        trades = filter_trades(
            trades,
            since=(since + "T00:00:00" if since else None),
            until=(until + "T23:59:59" if until else None),
        )
    results: Dict[str, SetupAnalysis] = {}
    for s in STRATEGIES:
        results[s] = analyze_setup(s, trades)
    ranked = sorted(results.values(), key=lambda x: x.setup_score, reverse=True)
    for i, item in enumerate(ranked, start=1):
        item.rank = i
    return results


def overall_setups_report() -> Dict[str, Any]:
    """Return full breakdowns for all strategies + ranking."""
    setups = analyze_all_setups()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategies": {k: v.to_dict() for k, v in setups.items()},
        "ranking": [v.strategy for v in sorted(setups.values(),
                                                key=lambda x: x.setup_score,
                                                reverse=True)],
    }


# =============================================================================
# PHASE-1 ACCEPTANCE: Setup analyzer sanity test
# =============================================================================

def acceptance_smoke_test() -> Dict[str, Any]:
    """Quick test that active strategies produce a non-empty breakdown."""
    base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    def _t(ticket, strat, profit, regime="RANGING", session="LONDON") -> TradeRecord:
        return TradeRecord(
            ticket=ticket,
            strategy=strat,
            direction="BUY" if profit >= 0 else "SELL",
            session=session,
            regime=regime,
            open_time=base_time.isoformat(),
            close_time=base_time.isoformat(),
            profit=profit,
            risk_percent=0.5,
            rr_achieved=2.0 if profit >= 0 else 1.0,
            duration_sec=300,
            is_win=profit > 0,
        )

    seed = [
        _t(1, "SMC", 10, "TRENDING", "OVERLAP"),
        _t(2, "SMC", -5, "RANGING", "LONDON"),
        _t(3, "DAILY", 50, "TRENDING", "LONDON"),
        _t(4, "DAILY", -3, "RANGING", "NEW_YORK"),
    ]
    setups = {s: analyze_setup(s, seed) for s in STRATEGIES}
    # Apply ranking within the smoke function as well.
    ranked = sorted(setups.values(), key=lambda x: x.setup_score, reverse=True)
    for i, item in enumerate(ranked, start=1):
        item.rank = i
    return {
        "expected_strategies_present": sorted(STRATEGIES),
        "ranking_invariant": all(
            setups[k].rank > 0 for k in STRATEGIES
        ),
        "analyze_setup_seed_smoke": [
            setups[s].to_dict() for s in STRATEGIES
        ],
    }
