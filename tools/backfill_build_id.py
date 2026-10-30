"""
One-time backfill: stamp build_id onto trade records written before this
field existed, and quarantine the untagged/corrupt rows found in
data/history/trades.csv during the FER3ON-FINAL-build1 audit.

Context (see core/settings.py BUILD_ID for the full writeup):
  - data/history/trades.csv had 57 rows with blank ticket + blank strategy,
    all timestamped within an ~8 second window (2026-07-27T01:14:31-39Z),
    carrying profit values that exactly match trades from a retired
    pre-merge bot version (2026-07-15..17). No live code path in this
    build produces that row shape -- persist_trade_log (trade_executor.py)
    always sets both fields, and log_trade() now hard-refuses to write a
    row without them (core/trade_logger.py). This is a one-off artifact,
    most likely produced while consolidating the three pre-merge versions'
    data folders, not a recurring bug.
  - The remaining 76 real (ticketed) records in truth_layer/trade_history.json
    and the corresponding rows in trades.csv split cleanly into two batches
    with a 10-day gap between them: 2026-07-15..17 (56 trades, retired
    pre-merge strategy logic) and 2026-07-27..28 (20 trades, this build).
    BUILD_DEPLOYED_AT (core/settings.py) sits exactly in that gap.

This script is idempotent -- safe to re-run; it only rewrites rows whose
build_id is currently blank.

Usage:
    python3 tools/backfill_build_id.py [--apply]

Without --apply it only prints what it would do (dry run).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import BUILD_ID, BUILD_DEPLOYED_AT  # noqa: E402
from core.data_integrity import HISTORY_COLUMNS, read_csv_records, dump_rows  # noqa: E402

TRADES_CSV = "data/history/trades.csv"
MT5_HISTORY_CSV = "data/history/mt5_trade_history.csv"
TRUTH_LAYER_JSON = "data/truth_layer/trade_history.json"
QUARANTINE_CSV = "data/history/legacy_untagged_quarantine.csv"

CUTOFF = datetime.fromisoformat(BUILD_DEPLOYED_AT)
LEGACY_LABEL = "LEGACY_PRE_BUILD1"


def _parse_dt(value: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def backfill_trades_csv(apply: bool) -> None:
    if not os.path.exists(TRADES_CSV):
        print(f"[skip] {TRADES_CSV} not found")
        return

    rows = read_csv_records(TRADES_CSV, HISTORY_COLUMNS)
    keep, quarantine = [], []

    for row in rows:
        if row.get("build_id"):
            keep.append(row)
            continue

        ticket = str(row.get("ticket") or "").strip()
        strategy = str(row.get("strategy") or "").strip()

        if not ticket and not strategy:
            # The 57-row artifact: untraceable to any position or build.
            quarantine.append(row)
            continue

        dt = _parse_dt(row.get("date", ""))
        row["build_id"] = BUILD_ID if (dt and dt >= CUTOFF) else LEGACY_LABEL
        keep.append(row)

    print(f"{TRADES_CSV}: {len(rows)} rows -> {len(keep)} kept, {len(quarantine)} quarantined")
    tagged = [r for r in keep if r.get("build_id") == BUILD_ID]
    legacy = [r for r in keep if r.get("build_id") == LEGACY_LABEL]
    print(f"  build_id={BUILD_ID}: {len(tagged)} rows")
    print(f"  build_id={LEGACY_LABEL}: {len(legacy)} rows")

    if not apply:
        return

    shutil.copy2(TRADES_CSV, TRADES_CSV + ".bak")
    dump_rows(TRADES_CSV, HISTORY_COLUMNS, keep)

    if quarantine:
        qa_columns = HISTORY_COLUMNS
        existing_quarantine = []
        if os.path.exists(QUARANTINE_CSV):
            existing_quarantine = read_csv_records(QUARANTINE_CSV, qa_columns)
        dump_rows(QUARANTINE_CSV, qa_columns, existing_quarantine + quarantine)
        print(f"  -> quarantined rows written to {QUARANTINE_CSV}")

    print(f"  -> backup of original saved to {TRADES_CSV}.bak")


def backfill_mt5_history_csv(apply: bool) -> None:
    if not os.path.exists(MT5_HISTORY_CSV):
        print(f"[skip] {MT5_HISTORY_CSV} not found")
        return

    with open(MT5_HISTORY_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if rows and "build_id" not in rows[0]:
        for row in rows:
            row["build_id"] = ""

    changed = 0
    for row in rows:
        if row.get("build_id"):
            continue
        dt = _parse_dt(row.get("close_time", "") or row.get("open_time", ""))
        row["build_id"] = BUILD_ID if (dt and dt >= CUTOFF) else LEGACY_LABEL
        changed += 1

    print(f"{MT5_HISTORY_CSV}: {len(rows)} rows, {changed} backfilled")

    if not apply or not rows:
        return

    shutil.copy2(MT5_HISTORY_CSV, MT5_HISTORY_CSV + ".bak")
    fieldnames = list(rows[0].keys())
    with open(MT5_HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> backup of original saved to {MT5_HISTORY_CSV}.bak")


def backfill_truth_layer_json(apply: bool) -> None:
    if not os.path.exists(TRUTH_LAYER_JSON):
        print(f"[skip] {TRUTH_LAYER_JSON} not found")
        return

    with open(TRUTH_LAYER_JSON, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    records = [json.loads(l) for l in lines]

    changed = 0
    for rec in records:
        if rec.get("build_id"):
            continue
        dt = _parse_dt(rec.get("close_time", "") or rec.get("open_time", ""))
        # ticket <= 100000 marks the synthetic bootstrap records seeded at
        # 2025-01-01 (entry_price=0, ticket 1-3) found during the audit --
        # distinct from real MT5-synced tickets, which are 11-digit numbers.
        if rec.get("ticket", 0) and rec["ticket"] <= 100000:
            rec["build_id"] = "SYNTHETIC_BOOTSTRAP"
        else:
            rec["build_id"] = BUILD_ID if (dt and dt >= CUTOFF) else LEGACY_LABEL
        changed += 1

    print(f"{TRUTH_LAYER_JSON}: {len(records)} records, {changed} backfilled")

    if not apply:
        return

    shutil.copy2(TRUTH_LAYER_JSON, TRUTH_LAYER_JSON + ".bak")
    with open(TRUTH_LAYER_JSON, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"  -> backup of original saved to {TRUTH_LAYER_JSON}.bak")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    print(f"BUILD_ID = {BUILD_ID}")
    print(f"Cutoff   = {CUTOFF.isoformat()}  (rows before this are tagged {LEGACY_LABEL})")
    print(f"Mode     = {'APPLY' if args.apply else 'DRY RUN (pass --apply to write)'}")
    print()

    backfill_trades_csv(args.apply)
    print()
    backfill_mt5_history_csv(args.apply)
    print()
    backfill_truth_layer_json(args.apply)


if __name__ == "__main__":
    main()
