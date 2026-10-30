#!/usr/bin/env python3
# =============================================================================
# FAIE — Historical Backtest Harness Runner
# =============================================================================
# Replays data/history/trades.csv through testing.faie_backtest.run_faie_backtest
# and writes a full JSON report to data/faie/backtest/. This is the quality
# gate Phase-2 spec §6/§7 names before Paper Trading is even considered —
# see docs/FAIE/PHASE_2_SPECIFICATION.md §6-§7 and
# docs/FAIE/PHASE_2_PROGRESS.md for what this report can and cannot claim
# given the historical data actually available (a proxy comparison against
# the direction traded, not a full unified_decide() replay — read
# testing/faie_backtest.py's module docstring before trusting a number
# from this report in isolation).
#
# Usage:
#   PYTHONPATH=. python3 run_faie_backtest.py [path/to/history.csv]
# =============================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from testing.faie_backtest import run_faie_backtest, DEFAULT_HISTORY_CSV


def main() -> int:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HISTORY_CSV
    report = run_faie_backtest(csv_path=csv_path)

    out_dir = Path("data/faie/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"backtest_report_{stamp}.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("=" * 70)
    print("FAIE HISTORICAL BACKTEST REPORT (advisory only — see docstrings")
    print("in testing/faie_backtest.py before treating this as conclusive)")
    print("=" * 70)
    print(f"Source:              {csv_path}")
    print(f"Status:               {report.status}")
    print(f"Total rows:           {report.total_rows}")
    print(f"Skipped rows:         {report.skipped_rows}")
    print(f"Evaluated rows:       {report.evaluated_rows}")
    print(f"Agreements:           {report.agreements}")
    print(f"Opposite disagreements: {report.opposite_disagreements}")
    print(f"Neutral calls:        {report.neutral_calls}")
    print(f"Agreement rate:       {report.agreement_rate * 100:.1f}%")
    print(f"Would have avoided:   {len(report.would_have_avoided_losses)} losing trades")
    print(f"Would have missed:    {len(report.would_have_missed_wins)} winning trades")
    if report.note:
        print(f"Note: {report.note}")
    print("-" * 70)
    print(f"Full report written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
