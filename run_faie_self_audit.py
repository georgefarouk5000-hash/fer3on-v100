#!/usr/bin/env python3
# =============================================================================
# FAIE — Self Audit Runner
# =============================================================================
# Builds a combined bias/drift/overfitting report from whatever FAIE decision
# history actually exists today and writes it to
# data/analytics/self_audit_<date>.json — see certification/self_audit.py
# and docs/FAIE/PHASE_2_SPECIFICATION.md §4.
#
# Data sources used automatically, in order of preference:
#   1. data/faie/shadow_log.jsonl — real decisions logged by the live loop
#      when FAIE_SHADOW_LOGGING_ENABLED=True (see §5 / core/settings.py).
#      Used for both bias detection and drift (chronological baseline vs
#      recent split of the same log).
#   2. testing/faie_backtest.py's chronological CSV split (in_sample vs
#      out_of_sample) over data/history/trades.csv — used for overfitting
#      detection, independent of whether the shadow log has accumulated yet.
#
# Usage:
#   PYTHONPATH=. python3 run_faie_self_audit.py
# =============================================================================

from __future__ import annotations

import sys

from certification.self_audit import (
    build_self_audit_report,
    write_self_audit_report,
    load_shadow_log_decisions,
)
from testing.faie_backtest import run_faie_backtest_by_period


def main() -> int:
    decisions = load_shadow_log_decisions()
    certification_metrics_by_period = run_faie_backtest_by_period()

    report = build_self_audit_report(
        decisions=decisions,
        certification_metrics_by_period=certification_metrics_by_period,
    )
    out_path = write_self_audit_report(report)

    print("=" * 70)
    print("FAIE SELF AUDIT REPORT")
    print("=" * 70)
    print(f"Shadow-log decisions found: {len(decisions)}")
    print(f"Bias:         status={report['bias']['status']:<18} flagged={report['bias'].get('flagged')}")
    print(f"Drift:        status={report['drift']['status']:<18} flagged_analysts={report['drift'].get('flagged_analysts')}")
    print(f"Overfitting:  status={report['overfitting']['status']:<18} flagged_metrics={report['overfitting'].get('flagged_metrics')}")
    if not decisions:
        print(
            "\nNote: no shadow_log.jsonl decisions found yet — bias/drift are "
            "INSUFFICIENT_DATA until FAIE_SHADOW_LOGGING_ENABLED runs in the "
            "live loop for a while (see docs/FAIE/PHASE_2_SPECIFICATION.md §5). "
            "Overfitting detection above used data/history/trades.csv directly "
            "and does not need the shadow log."
        )
    print("-" * 70)
    print(f"Full report written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
