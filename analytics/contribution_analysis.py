# =============================================================================
# FER3ON V3+++ — PHASE 2 | MODULE CONTRIBUTION ANALYSIS
# =============================================================================
# Measures the actual statistical contribution of each signal module:
#   SMC / Liquidity / Structure / News / MTF
#
# Method:
#   1. Load closed trade history from Truth Layer.
#   2. Load closed decision snapshots from data/analytics/decision_snapshots/.
#   3. Join by ticket number.
#   4. For each module, compute metrics when module was present vs absent.
#   5. Compute delta vs baseline (no-module trades).
#   6. Produce a Contribution Report — advisory only.
#
# SAFETY CONTRACT:
#   ✅ Read-only
#   ✅ No imports from confidence_engine, adaptive_weighting, or risk_manager
#   ✅ No weights generated or written to any live config
#   ✅ All outputs → data/analytics/phase2/contributions/
#   ✅ advisory_only = True on every output object
# =============================================================================

from __future__ import annotations

import glob
import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from analytics.performance_repository import get_all_trades
from analytics.truth_layer import TradeRecord, compute_metrics, Metrics
from core.settings import (
    PHASE2_CONTRIB_DIR,
    PHASE2_MIN_SAMPLE_PER_BUCKET,
)

CLOSED_SNAPSHOTS_DIR = "data/analytics/decision_snapshots"

# Module presence keys as they appear in decision snapshots
MODULE_KEYS: Dict[str, List[str]] = {
    "SMC":        ["choch_state", "choch_strength"],       # present if choch_state != "NONE"
    "Liquidity":  ["liq_map_score", "liq_map_dir"],        # present if liq_map_score > 0
    "Structure":  ["mtf_structural"],                       # present if mtf_structural == True
    "News":       ["news_score"],                           # present if news_score is not None
    "MTF":        ["mtf_strength"],                         # present if mtf_strength > 0
}

LABEL_OK           = "EDGE_CONFIRMED"
LABEL_WEAK         = "WEAK_EDGE"
LABEL_INSUFFICIENT = "INSUFFICIENT_SAMPLE"


# =============================================================================
# SNAPSHOT LOADING & JOIN
# =============================================================================

def _load_closed_snapshots() -> Dict[int, Dict[str, Any]]:
    """Load all closed trade snapshots keyed by ticket number."""
    out: Dict[int, Dict[str, Any]] = {}
    if not os.path.isdir(CLOSED_SNAPSHOTS_DIR):
        return out
    for fpath in glob.glob(os.path.join(CLOSED_SNAPSHOTS_DIR, "*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                snap = json.load(f)
            ticket = int(snap.get("ticket") or snap.get("close_ticket") or 0)
            if ticket:
                out[ticket] = snap
        except Exception:
            continue
    return out


def _detect_module_presence(snap: Dict[str, Any]) -> Dict[str, bool]:
    """
    Return a dict {module_name: is_present} for each known module.
    Presence rules are deliberately conservative.
    """
    result: Dict[str, bool] = {}

    # SMC: CHoCH was detected (not NONE/WEAK)
    choch = str(snap.get("choch_state") or "NONE").upper()
    result["SMC"] = choch not in ("NONE", "")

    # Liquidity: liquidity map gave a directional score
    liq = snap.get("liq_map_score")
    liq_dir = str(snap.get("liq_map_dir") or "").upper()
    result["Liquidity"] = (
        liq is not None and float(liq) > 0 and liq_dir not in ("", "NONE")
    )

    # Structure: MTF structural alignment confirmed
    result["Structure"] = bool(snap.get("mtf_structural"))

    # News: news module provided a non-default score
    news = snap.get("news_score")
    result["News"] = news is not None and float(news) != 50.0

    # MTF: multi-timeframe strength > 0
    mtf = snap.get("mtf_strength")
    result["MTF"] = mtf is not None and float(mtf) > 0

    return result


# =============================================================================
# CONTRIBUTION METRICS
# =============================================================================

@dataclass
class ModuleContribution:
    module: str
    trades_with_module: int
    trades_without_module: int
    win_rate_with: float
    win_rate_without: float
    win_rate_delta: float
    expectancy_with: float
    expectancy_without: float
    expectancy_delta: float
    profit_factor_with: Optional[float]
    profit_factor_without: Optional[float]
    net_pnl_with: float
    net_pnl_without: float
    sample_label: str
    verdict: str            # POSITIVE / NEGATIVE / NEUTRAL / INSUFFICIENT
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _classify_sample(count: int) -> str:
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET:
        return LABEL_INSUFFICIENT
    if count < PHASE2_MIN_SAMPLE_PER_BUCKET * 3:
        return LABEL_WEAK
    return LABEL_OK


def _verdict(wr_delta: float, exp_delta: float, sample_label: str) -> str:
    if sample_label == LABEL_INSUFFICIENT:
        return "INSUFFICIENT"
    if wr_delta > 0.05 and exp_delta > 0:
        return "POSITIVE"
    if wr_delta < -0.05 or exp_delta < -0.5:
        return "NEGATIVE"
    return "NEUTRAL"


def _compute_module_contribution(
    module: str,
    joined: List[Tuple[TradeRecord, Dict[str, bool]]],
) -> ModuleContribution:
    with_module = [t for t, flags in joined if flags.get(module, False)]
    without_module = [t for t, flags in joined if not flags.get(module, False)]

    def pf_or_none(m: Metrics) -> Optional[float]:
        return m.profit_factor if m.profit_factor != float("inf") else None

    m_with    = compute_metrics(with_module)
    m_without = compute_metrics(without_module)

    sample_label = _classify_sample(len(with_module))

    wr_delta  = m_with.win_rate  - m_without.win_rate
    exp_delta = m_with.expectancy - m_without.expectancy

    return ModuleContribution(
        module=module,
        trades_with_module=len(with_module),
        trades_without_module=len(without_module),
        win_rate_with=m_with.win_rate,
        win_rate_without=m_without.win_rate,
        win_rate_delta=wr_delta,
        expectancy_with=m_with.expectancy,
        expectancy_without=m_without.expectancy,
        expectancy_delta=exp_delta,
        profit_factor_with=pf_or_none(m_with),
        profit_factor_without=pf_or_none(m_without),
        net_pnl_with=m_with.net_pnl,
        net_pnl_without=m_without.net_pnl,
        sample_label=sample_label,
        verdict=_verdict(wr_delta, exp_delta, sample_label),
    )


# =============================================================================
# FULL CONTRIBUTION REPORT
# =============================================================================

@dataclass
class ContributionReport:
    generated_at: str
    total_trades_in_truth_layer: int
    total_trades_matched_to_snapshots: int
    match_rate: float
    modules: List[ModuleContribution]
    snapshot_coverage_note: str
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_trades_in_truth_layer": self.total_trades_in_truth_layer,
            "total_trades_matched_to_snapshots": self.total_trades_matched_to_snapshots,
            "match_rate": self.match_rate,
            "snapshot_coverage_note": self.snapshot_coverage_note,
            "advisory_only": self.advisory_only,
            "not_applied_live": self.not_applied_live,
            "modules": [m.to_dict() for m in self.modules],
        }


def build_contribution_report(trades=None) -> ContributionReport:
    """
    Build Module Contribution Report.
    Joins Truth Layer trades with closed decision snapshots by ticket.
    Only matched trades are analysed; unmatched are noted in coverage.
    """
    if trades is None:
        trades = get_all_trades()

    snapshots = _load_closed_snapshots()
    total_tl = len(trades)

    joined: List[Tuple[TradeRecord, Dict[str, bool]]] = []
    matched_tickets: Set[int] = set()

    for t in trades:
        snap = snapshots.get(t.ticket)
        if snap:
            flags = _detect_module_presence(snap)
            joined.append((t, flags))
            matched_tickets.add(t.ticket)

    matched = len(joined)
    match_rate = (matched / total_tl) if total_tl > 0 else 0.0

    if match_rate < 0.3:
        note = (
            f"Only {match_rate:.0%} of Truth Layer trades matched to decision snapshots. "
            f"Contribution analysis may be limited. "
            f"To improve coverage, ensure decision snapshots are enriched "
            f"with module signals at trade open (see core/decision_snapshot.py)."
        )
    elif match_rate < 0.7:
        note = (
            f"{match_rate:.0%} of trades matched. "
            f"Results are directional — increase snapshot coverage for higher confidence."
        )
    else:
        note = f"{match_rate:.0%} match rate — sufficient for contribution analysis."

    module_names = list(MODULE_KEYS.keys())
    contributions = [
        _compute_module_contribution(m, joined)
        for m in module_names
    ]

    return ContributionReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trades_in_truth_layer=total_tl,
        total_trades_matched_to_snapshots=matched,
        match_rate=round(match_rate, 4),
        modules=contributions,
        snapshot_coverage_note=note,
    )


# =============================================================================
# PERSIST
# =============================================================================

def persist_contribution_report(report: Optional[ContributionReport] = None) -> str:
    if report is None:
        report = build_contribution_report()
    os.makedirs(PHASE2_CONTRIB_DIR, exist_ok=True)
    path = os.path.join(PHASE2_CONTRIB_DIR, "module_contribution_report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path


# =============================================================================
# CLI
# =============================================================================

def print_contribution_summary(report: Optional[ContributionReport] = None) -> None:
    if report is None:
        report = build_contribution_report()
    print(f"\n{'='*70}")
    print(f"MODULE CONTRIBUTION ANALYSIS  [{report.generated_at[:19]}]")
    print(f"advisory_only=True  not_applied_live=True")
    print(f"TL Trades={report.total_trades_in_truth_layer}  "
          f"Matched={report.total_trades_matched_to_snapshots}  "
          f"Match Rate={report.match_rate:.0%}")
    print(f"Coverage: {report.snapshot_coverage_note}")
    print(f"{'='*70}")
    print(f"  {'Module':<14} {'N(with)':<9} {'WR(with)':<10} {'WR(delta)':<12} "
          f"{'Exp(delta)':<13} {'Verdict'}")
    print(f"  {'-'*66}")
    for m in report.modules:
        wr_d = f"{m.win_rate_delta:+.1%}"
        exp_d = f"{m.expectancy_delta:+.2f}"
        print(
            f"  {m.module:<14} {m.trades_with_module:<9} "
            f"{m.win_rate_with:.1%}     {wr_d:<12} {exp_d:<13} "
            f"{m.verdict}  [{m.sample_label}]"
        )
    print()


if __name__ == "__main__":
    r = build_contribution_report()
    print_contribution_summary(r)
    path = persist_contribution_report(r)
    print(f"Saved → {path}")
