#!/usr/bin/env python3
# =============================================================================
# FER3ON V3+++ — PHASE 2 | PERFORMANCE INTELLIGENCE REPORT GENERATOR
# =============================================================================
# Runs all Phase-2 analytics and persists results to:
#   data/analytics/phase2/reports/
#   data/analytics/phase2/rankings/
#   data/analytics/phase2/contributions/
#   data/analytics/phase2/shadow/
#
# Usage:
#   python tools/generate_performance_intelligence_reports.py
#   python tools/generate_performance_intelligence_reports.py --quiet
#   python tools/generate_performance_intelligence_reports.py --module session
#
# SAFETY CONTRACT:
#   ✅ Post-trade analysis only
#   ✅ Read-only from Truth Layer
#   ✅ No runtime influence
#   ✅ Output is JSON + Markdown summary in phase2/ dirs only
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add project root to path (when run as tool from project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from analytics.performance_repository import (
    get_all_trades,
    get_overall_metrics,
    safe_metrics_dict,
)
from analytics.session_edge_analysis import (
    analyse_sessions,
    persist_session_ranking,
    print_session_summary,
)
from analytics.regime_edge_analysis import (
    analyse_regimes,
    persist_regime_ranking,
    print_regime_summary,
)
from analytics.portfolio_statistics import (
    build_portfolio_statistics,
    persist_portfolio_statistics,
    print_portfolio_summary,
)
from analytics.contribution_analysis import (
    build_contribution_report,
    persist_contribution_report,
    print_contribution_summary,
)
from analytics.adaptive_shadow_prep import (
    build_shadow_state,
    persist_shadow_state,
    print_shadow_summary,
)
from core.settings import (
    PHASE2_REPORTS_DIR,
    PHASE2_ANALYTICS_DIR,
)


# =============================================================================
# REPORT STATUS
# =============================================================================

class ReportStatus:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []

    def record(self, module: str, path: str, success: bool, error: str = "") -> None:
        self.results.append({
            "module": module,
            "path": path,
            "success": success,
            "error": error,
        })

    def print_summary(self) -> None:
        print(f"\n{'='*60}")
        print("PHASE 2 REPORT GENERATION SUMMARY")
        print(f"{'='*60}")
        for r in self.results:
            icon = "✅" if r["success"] else "❌"
            print(f"  {icon} {r['module']:<30} → {r['path']}")
            if r["error"]:
                print(f"       ERROR: {r['error']}")
        ok = sum(1 for r in self.results if r["success"])
        print(f"\n  {ok}/{len(self.results)} modules completed successfully.")
        print()


# =============================================================================
# MARKDOWN SUMMARY
# =============================================================================

def _pf_str(pf) -> str:
    if pf is None:
        return "∞"
    return f"{pf:.2f}"


def generate_markdown_summary(
    trades,
    session_ranking,
    regime_ranking,
    portfolio_stats,
    contribution_report,
    shadow_state,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    overall = get_overall_metrics(trades)
    lines: List[str] = []

    lines.append(f"# FER3ON V3+++ — Phase 2 Performance Intelligence")
    lines.append(f"Generated: {now}  |  Trades analysed: {len(trades)}")
    lines.append(f"\n> advisory_only=True  not_applied_live=True")

    # Overall
    lines.append(f"\n## Overall Portfolio")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Trades | {overall.total_trades} |")
    lines.append(f"| Win Rate | {overall.win_rate:.1%} |")
    lines.append(f"| Profit Factor | {_pf_str(overall.profit_factor if overall.profit_factor != float('inf') else None)} |")
    lines.append(f"| Expectancy | {overall.expectancy:+.2f} |")
    lines.append(f"| Net PnL | {overall.net_pnl:+.2f} |")
    lines.append(f"| Max Drawdown | {overall.max_drawdown:.2f} |")
    lines.append(f"| Best Trade | {overall.best_trade:+.2f} |")
    lines.append(f"| Worst Trade | {overall.worst_trade:+.2f} |")
    lines.append(f"| Max Consec. Losses | {overall.max_consecutive_losses} |")

    # Session Rankings
    lines.append(f"\n## Session Edge Ranking")
    lines.append(f"| Rank | Session | Trades | WR | PF | Expectancy | Status |")
    lines.append(f"|------|---------|--------|----|----|-----------|--------|")
    ranked = sorted(session_ranking.sessions, key=lambda s: s.rank if s.rank > 0 else 999)
    for s in ranked:
        rank_str = f"#{s.rank}" if s.rank > 0 else "-"
        lines.append(
            f"| {rank_str} | {s.session} | {s.total_trades} | "
            f"{s.win_rate:.1%} | {_pf_str(s.profit_factor)} | "
            f"{s.expectancy:+.2f} | {s.sample_label} |"
        )

    # Regime Rankings
    lines.append(f"\n## Regime Edge Ranking")
    lines.append(f"| Rank | Regime | Trades | WR | PF | Expectancy | Type | Status |")
    lines.append(f"|------|--------|--------|----|----|-----------|------|--------|")
    r_ranked = sorted(regime_ranking.regimes, key=lambda r: r.rank if r.rank > 0 else 999)
    for r in r_ranked:
        rank_str = f"#{r.rank}" if r.rank > 0 else "-"
        live_tag = "live" if r.is_live_label else "analytic"
        lines.append(
            f"| {rank_str} | {r.regime} | {r.total_trades} | "
            f"{r.win_rate:.1%} | {_pf_str(r.profit_factor)} | "
            f"{r.expectancy:+.2f} | {live_tag} | {r.sample_label} |"
        )

    # Module Contribution
    lines.append(f"\n## Module Contribution Analysis")
    lines.append(f"Coverage: {contribution_report.snapshot_coverage_note}")
    lines.append(f"\n| Module | N(with) | WR(with) | WR(delta) | Exp(delta) | Verdict |")
    lines.append(f"|--------|---------|----------|-----------|------------|---------|")
    for m in contribution_report.modules:
        lines.append(
            f"| {m.module} | {m.trades_with_module} | "
            f"{m.win_rate_with:.1%} | {m.win_rate_delta:+.1%} | "
            f"{m.expectancy_delta:+.2f} | {m.verdict} [{m.sample_label}] |"
        )

    # Exposure
    exp = portfolio_stats.exposure_diagnostics
    lines.append(f"\n## Exposure Diagnostics")
    if exp.get("concentration_flag"):
        lines.append(f"\n⚠ **Concentration Warning:**")
        for note in exp.get("concentration_notes", []):
            lines.append(f"- {note}")
    else:
        lines.append(f"\n✅ No concentration issues detected.")

    # Shadow Calibration Readiness
    lines.append(f"\n## Adaptive Shadow Calibration Readiness")
    lines.append(f"shadow_only=True  activated=False")
    lines.append(f"\n| Bucket | Key | Suggestion | Confidence |")
    lines.append(f"|--------|-----|------------|------------|")
    for c in shadow_state.calibration_candidates:
        conf = "✓ HIGH" if c.sufficient_confidence else "? LOW"
        lines.append(
            f"| {c.bucket_type} | {c.bucket_key} | {c.suggestion_type} | {conf} |"
        )

    return "\n".join(lines)


# =============================================================================
# MAIN RUNNER
# =============================================================================

def run_all(quiet: bool = False, modules: Optional[List[str]] = None) -> ReportStatus:
    status = ReportStatus()
    trades = get_all_trades()
    run_all_modules = not modules

    def should_run(name: str) -> bool:
        return run_all_modules or name in modules

    # --- Session ---
    if should_run("session"):
        try:
            r = analyse_sessions(trades)
            path = persist_session_ranking(r)
            if not quiet:
                print_session_summary(r)
            status.record("Session Edge Analysis", path, True)
        except Exception as e:
            status.record("Session Edge Analysis", "", False, traceback.format_exc(limit=3))

    # --- Regime ---
    if should_run("regime"):
        try:
            r = analyse_regimes(trades)
            path = persist_regime_ranking(r)
            if not quiet:
                print_regime_summary(r)
            status.record("Regime Edge Analysis", path, True)
        except Exception as e:
            status.record("Regime Edge Analysis", "", False, traceback.format_exc(limit=3))

    # --- Portfolio ---
    if should_run("portfolio"):
        try:
            s = build_portfolio_statistics(trades)
            path = persist_portfolio_statistics(s)
            if not quiet:
                print_portfolio_summary(s)
            status.record("Portfolio Statistics", path, True)
        except Exception as e:
            status.record("Portfolio Statistics", "", False, traceback.format_exc(limit=3))

    # --- Contribution ---
    if should_run("contribution"):
        try:
            r = build_contribution_report(trades)
            path = persist_contribution_report(r)
            if not quiet:
                print_contribution_summary(r)
            status.record("Module Contribution Analysis", path, True)
        except Exception as e:
            status.record("Module Contribution Analysis", "", False, traceback.format_exc(limit=3))

    # --- Shadow ---
    if should_run("shadow"):
        try:
            s = build_shadow_state(trades)
            sp, cp = persist_shadow_state(s)
            if not quiet:
                print_shadow_summary(s)
            status.record("Adaptive Shadow Prep", sp, True)
        except Exception as e:
            status.record("Adaptive Shadow Prep", "", False, traceback.format_exc(limit=3))

    # --- Markdown Summary ---
    if run_all_modules:
        try:
            session_r  = analyse_sessions(trades)
            regime_r   = analyse_regimes(trades)
            port_s     = build_portfolio_statistics(trades)
            contrib_r  = build_contribution_report(trades)
            shadow_s   = build_shadow_state(trades)
            md = generate_markdown_summary(
                trades, session_r, regime_r, port_s, contrib_r, shadow_s
            )
            os.makedirs(PHASE2_REPORTS_DIR, exist_ok=True)
            md_path = os.path.join(PHASE2_REPORTS_DIR, "phase2_summary.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            status.record("Markdown Summary", md_path, True)
        except Exception as e:
            status.record("Markdown Summary", "", False, traceback.format_exc(limit=3))

    return status


def main():
    parser = argparse.ArgumentParser(
        description="FER3ON Phase 2 — Performance Intelligence Report Generator"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress console output"
    )
    parser.add_argument(
        "--module",
        nargs="+",
        choices=["session", "regime", "portfolio", "contribution", "shadow"],
        help="Run specific module(s) only",
    )
    args = parser.parse_args()

    if not args.quiet:
        print(f"\n{'='*65}")
        print(f"FER3ON V3+++ — PHASE 2 PERFORMANCE INTELLIGENCE")
        print(f"advisory_only=True  not_applied_live=True")
        print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*65}\n")

    status = run_all(quiet=args.quiet, modules=args.module)
    status.print_summary()


if __name__ == "__main__":
    main()
