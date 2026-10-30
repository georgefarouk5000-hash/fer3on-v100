# =============================================================================
# FER3ON V3+++ — PHASE 2 | REGIME EDGE ANALYSIS
# =============================================================================
# Ranks market regimes (Trending / Ranging / Volatile / Crisis / Unknown)
# by actual statistical edge from Truth Layer history.
#
# SAFETY CONTRACT:
#   ✅ Read-only — no writes to runtime files
#   ✅ No imports from core/market_regime.py that would alter live labels
#   ✅ Uses existing regime labels as-is from trade records
#   ✅ LOW_VOLATILITY is a derived analytic bucket only (not a live label)
#   ✅ advisory_only = True on every output object
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analytics.performance_repository import (
    get_all_trades,
    get_regime_breakdown,
    safe_metrics_dict,
)
from analytics.truth_layer import Metrics, TradeRecord
from core.settings import (
    PHASE2_RANKINGS_DIR,
    PHASE2_MIN_SAMPLE_PER_BUCKET,
)

# Live regime labels used by core/market_regime.py
LIVE_REGIMES = ["TRENDING", "RANGING", "VOLATILE", "CRISIS", "UNKNOWN"]

# Analytic-only derived bucket — never written back to live state
ANALYTIC_LOW_VOL_LABEL = "LOW_VOLATILITY_ANALYTIC"

LABEL_OK           = "EDGE_CONFIRMED"
LABEL_WEAK         = "WEAK_EDGE"
LABEL_INSUFFICIENT = "INSUFFICIENT_SAMPLE"
LABEL_NO_TRADES    = "NO_TRADES"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RegimeEdge:
    regime: str
    is_live_label: bool          # True = comes directly from market_regime; False = analytic bucket
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: Optional[float]
    expectancy: float
    max_drawdown: float
    avg_rr: float
    net_pnl: float
    avg_regime_strength: float
    sample_label: str
    rank: int = 0
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegimeEdgeRanking:
    generated_at: str
    total_trades_analysed: int
    min_sample_threshold: int
    regimes: List[RegimeEdge]
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_trades_analysed": self.total_trades_analysed,
            "min_sample_threshold": self.min_sample_threshold,
            "advisory_only": self.advisory_only,
            "not_applied_live": self.not_applied_live,
            "regimes": [r.to_dict() for r in self.regimes],
        }


# =============================================================================
# HELPERS
# =============================================================================

def _classify_sample(count: int) -> str:
    if count == 0:
        return LABEL_NO_TRADES
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET:
        return LABEL_INSUFFICIENT
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET * 3:
        return LABEL_WEAK
    return LABEL_OK


def _avg_regime_strength(trades: List[TradeRecord]) -> float:
    vals = [t.regime_strength for t in trades if t.regime_strength]
    return sum(vals) / len(vals) if vals else 0.0


def _regime_edge_from_trades(
    regime: str, trades: List[TradeRecord], is_live: bool
) -> RegimeEdge:
    from analytics.truth_layer import compute_metrics
    m = compute_metrics(trades)
    pf = m.profit_factor if m.profit_factor != float("inf") else None
    return RegimeEdge(
        regime=regime,
        is_live_label=is_live,
        total_trades=m.total_trades,
        wins=m.wins,
        losses=m.losses,
        win_rate=m.win_rate,
        profit_factor=pf,
        expectancy=m.expectancy,
        max_drawdown=m.max_drawdown,
        avg_rr=m.avg_rr,
        net_pnl=m.net_pnl,
        avg_regime_strength=_avg_regime_strength(trades),
        sample_label=_classify_sample(m.total_trades),
    )


def _derive_low_vol_bucket(
    trades: List[TradeRecord],
) -> Optional[RegimeEdge]:
    """
    Analytic-only: RANGING trades with low regime_strength (< 0.35) are
    grouped into a LOW_VOLATILITY_ANALYTIC diagnostic bucket.
    This bucket is NEVER written back to any live label or setting.
    """
    low_vol = [
        t for t in trades
        if (t.regime or "").upper() == "RANGING"
        and t.regime_strength < 0.35
    ]
    if not low_vol:
        return None
    edge = _regime_edge_from_trades(ANALYTIC_LOW_VOL_LABEL, low_vol, is_live=False)
    return edge


def _rank_regimes(regimes: List[RegimeEdge]) -> List[RegimeEdge]:
    eligible = [
        r for r in regimes
        if r.sample_label in (LABEL_OK, LABEL_WEAK)
    ]
    eligible.sort(key=lambda r: (r.expectancy, r.win_rate), reverse=True)
    rank = 1
    for r in eligible:
        r.rank = rank
        rank += 1
    return regimes


# =============================================================================
# CORE ANALYSIS
# =============================================================================

def analyse_regimes(
    trades=None,
) -> RegimeEdgeRanking:
    """
    Analyse regime edge from Truth Layer trades.
    Returns RegimeEdgeRanking — advisory only, never fed to runtime.
    """
    if trades is None:
        trades = get_all_trades()

    from collections import defaultdict
    grouped: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in trades:
        key = (t.regime or "UNKNOWN").upper()
        grouped[key].append(t)

    regimes: List[RegimeEdge] = []

    # Build edges for all live labels
    covered = set()
    for regime_key, bucket_trades in grouped.items():
        is_live = regime_key in LIVE_REGIMES
        edge = _regime_edge_from_trades(regime_key, bucket_trades, is_live)
        regimes.append(edge)
        covered.add(regime_key)

    # Fill in known live labels with zero trades
    for regime in LIVE_REGIMES:
        if regime not in covered:
            regimes.append(RegimeEdge(
                regime=regime,
                is_live_label=True,
                total_trades=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                profit_factor=None,
                expectancy=0.0,
                max_drawdown=0.0,
                avg_rr=0.0,
                net_pnl=0.0,
                avg_regime_strength=0.0,
                sample_label=LABEL_NO_TRADES,
            ))

    # Add derived analytic bucket (not a live label)
    low_vol = _derive_low_vol_bucket(trades)
    if low_vol:
        regimes.append(low_vol)

    regimes = _rank_regimes(regimes)

    return RegimeEdgeRanking(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trades_analysed=len(trades),
        min_sample_threshold=PHASE2_MIN_SAMPLE_PER_BUCKET,
        regimes=regimes,
    )


# =============================================================================
# PERSIST
# =============================================================================

def persist_regime_ranking(ranking: Optional[RegimeEdgeRanking] = None) -> str:
    if ranking is None:
        ranking = analyse_regimes()
    os.makedirs(PHASE2_RANKINGS_DIR, exist_ok=True)
    path = os.path.join(PHASE2_RANKINGS_DIR, "regime_edge_ranking.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ranking.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path


# =============================================================================
# CLI
# =============================================================================

def print_regime_summary(ranking: Optional[RegimeEdgeRanking] = None) -> None:
    if ranking is None:
        ranking = analyse_regimes()
    print(f"\n{'='*65}")
    print(f"REGIME EDGE RANKING  [{ranking.generated_at[:19]}]")
    print(f"Total trades: {ranking.total_trades_analysed}  |  Min sample: {ranking.min_sample_threshold}")
    print(f"advisory_only=True  not_applied_live=True")
    print(f"{'='*65}")
    ranked = sorted(
        ranking.regimes,
        key=lambda r: (r.rank if r.rank > 0 else 999, r.regime),
    )
    for r in ranked:
        rank_str = f"#{r.rank}" if r.rank > 0 else "  -"
        pf_str = f"{r.profit_factor:.2f}" if r.profit_factor is not None else "N/A"
        live_tag = "(live)" if r.is_live_label else "(analytic)"
        print(
            f"  {rank_str:<4} {r.regime:<28} "
            f"N={r.total_trades:<4} WR={r.win_rate:.1%}  "
            f"PF={pf_str:<6} Exp={r.expectancy:+.2f}  "
            f"DD={r.max_drawdown:.2f}  {live_tag}  [{r.sample_label}]"
        )
    print()


if __name__ == "__main__":
    r = analyse_regimes()
    print_regime_summary(r)
    path = persist_regime_ranking(r)
    print(f"Saved → {path}")
