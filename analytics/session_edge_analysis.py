# =============================================================================
# FER3ON V3+++ — PHASE 2 | SESSION EDGE ANALYSIS
# =============================================================================
# Ranks trading sessions (Asia / London / New York / Overlap) by actual
# statistical edge derived from Truth Layer history.
#
# SAFETY CONTRACT:
#   ✅ Read-only — no writes to runtime files
#   ✅ No imports from core runtime (main, session_intelligence, risk, etc.)
#   ✅ Output is advisory_only — never fed back to runtime decisions
#   ✅ INSUFFICIENT_SAMPLE returned instead of misleading stats
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analytics.performance_repository import (
    get_all_trades,
    get_session_breakdown,
    safe_metrics_dict,
    describe_metrics,
)
from analytics.truth_layer import Metrics
from core.settings import (
    PHASE2_RANKINGS_DIR,
    PHASE2_MIN_SAMPLE_PER_BUCKET,
)

# Known sessions in priority display order
KNOWN_SESSIONS = ["ASIA", "LONDON", "NEWYORK", "OVERLAP"]

# Ranking confidence labels
LABEL_OK               = "EDGE_CONFIRMED"
LABEL_WEAK             = "WEAK_EDGE"
LABEL_INSUFFICIENT     = "INSUFFICIENT_SAMPLE"
LABEL_NO_TRADES        = "NO_TRADES"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SessionEdge:
    session: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: Optional[float]   # None when insufficient sample
    expectancy: float
    max_drawdown: float
    avg_rr: float
    net_pnl: float
    sample_label: str        # EDGE_CONFIRMED / WEAK_EDGE / INSUFFICIENT_SAMPLE / NO_TRADES
    rank: int = 0            # 1 = best; 0 = unranked (insufficient sample)
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class SessionEdgeRanking:
    generated_at: str
    total_trades_analysed: int
    min_sample_threshold: int
    sessions: List[SessionEdge]
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_trades_analysed": self.total_trades_analysed,
            "min_sample_threshold": self.min_sample_threshold,
            "advisory_only": self.advisory_only,
            "not_applied_live": self.not_applied_live,
            "sessions": [s.to_dict() for s in self.sessions],
        }


# =============================================================================
# CORE ANALYSIS
# =============================================================================

def _classify_sample(count: int) -> str:
    if count == 0:
        return LABEL_NO_TRADES
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET:
        return LABEL_INSUFFICIENT
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET * 3:
        return LABEL_WEAK
    return LABEL_OK


def _session_edge_from_metrics(session: str, m: Metrics) -> SessionEdge:
    sample_label = _classify_sample(m.total_trades)
    pf = m.profit_factor if m.profit_factor != float("inf") else None
    return SessionEdge(
        session=session,
        total_trades=m.total_trades,
        wins=m.wins,
        losses=m.losses,
        win_rate=m.win_rate,
        profit_factor=pf,
        expectancy=m.expectancy,
        max_drawdown=m.max_drawdown,
        avg_rr=m.avg_rr,
        net_pnl=m.net_pnl,
        sample_label=sample_label,
    )


def _rank_sessions(edges: List[SessionEdge]) -> List[SessionEdge]:
    """
    Rank only sessions with EDGE_CONFIRMED or WEAK_EDGE.
    Ranking key: expectancy (primary), win_rate (secondary).
    Insufficient/no-trade sessions get rank=0.
    """
    eligible = [
        e for e in edges
        if e.sample_label in (LABEL_OK, LABEL_WEAK)
    ]
    eligible.sort(key=lambda e: (e.expectancy, e.win_rate), reverse=True)
    rank = 1
    for e in eligible:
        e.rank = rank
        rank += 1
    return edges


def analyse_sessions(
    trades=None,
) -> SessionEdgeRanking:
    """
    Run Session Edge Analysis over Truth Layer trades.
    Returns a SessionEdgeRanking — advisory only, never fed to runtime.
    """
    if trades is None:
        trades = get_all_trades()

    breakdown = get_session_breakdown(trades)
    total = len(trades)

    edges: List[SessionEdge] = []

    # Include known sessions even if no trades recorded
    covered = set()
    for session_key, metrics in breakdown.items():
        edge = _session_edge_from_metrics(session_key, metrics)
        edges.append(edge)
        covered.add(session_key.upper())

    for session in KNOWN_SESSIONS:
        if session not in covered:
            edges.append(SessionEdge(
                session=session,
                total_trades=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                profit_factor=None,
                expectancy=0.0,
                max_drawdown=0.0,
                avg_rr=0.0,
                net_pnl=0.0,
                sample_label=LABEL_NO_TRADES,
            ))

    edges = _rank_sessions(edges)

    return SessionEdgeRanking(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trades_analysed=total,
        min_sample_threshold=PHASE2_MIN_SAMPLE_PER_BUCKET,
        sessions=edges,
    )


# =============================================================================
# PERSIST
# =============================================================================

def persist_session_ranking(ranking: Optional[SessionEdgeRanking] = None) -> str:
    """Write ranking to phase2/rankings/session_edge_ranking.json. Returns path."""
    if ranking is None:
        ranking = analyse_sessions()
    os.makedirs(PHASE2_RANKINGS_DIR, exist_ok=True)
    path = os.path.join(PHASE2_RANKINGS_DIR, "session_edge_ranking.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ranking.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path


# =============================================================================
# CLI / quick display
# =============================================================================

def print_session_summary(ranking: Optional[SessionEdgeRanking] = None) -> None:
    if ranking is None:
        ranking = analyse_sessions()
    print(f"\n{'='*60}")
    print(f"SESSION EDGE RANKING  [{ranking.generated_at[:19]}]")
    print(f"Total trades: {ranking.total_trades_analysed}  |  Min sample: {ranking.min_sample_threshold}")
    print(f"advisory_only=True  not_applied_live=True")
    print(f"{'='*60}")
    ranked = sorted(ranking.sessions, key=lambda s: (s.rank if s.rank > 0 else 999, s.session))
    for s in ranked:
        rank_str = f"#{s.rank}" if s.rank > 0 else "  -"
        pf_str = f"{s.profit_factor:.2f}" if s.profit_factor is not None else "N/A"
        print(
            f"  {rank_str:<4} {s.session:<12} "
            f"N={s.total_trades:<4} WR={s.win_rate:.1%}  "
            f"PF={pf_str:<6} Exp={s.expectancy:+.2f}  "
            f"DD={s.max_drawdown:.2f}  [{s.sample_label}]"
        )
    print()


if __name__ == "__main__":
    r = analyse_sessions()
    print_session_summary(r)
    path = persist_session_ranking(r)
    print(f"Saved → {path}")
