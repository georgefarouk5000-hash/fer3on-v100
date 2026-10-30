"""
One-time cleanup: remove duplicate truth_layer entries caused by the
ticket-key mismatch bug (core/mt5_history_sync.py used deal.ticket instead
of close_ticket when writing TradeRecord -- see the fix and its comment for
the full writeup). Because analytics/csv_truth_bridge.py dedupes against
trades.csv by ticket, and the two ticket schemes never matched, every real
trade was silently duplicated: once by mt5_history_sync (correct build_id,
keyed by the wrong ticket) and once by the bridge (correct ticket, but
build_id="" since the bridge didn't carry it through either -- also now
fixed).

This script only removes the *bridge-created* duplicate half of each pair
(extra.source == "csv_truth_bridge", build_id == "") when a matching
properly-tagged entry (extra.source == "mt5_history_sync") exists with the
same (strategy, profit, lot, close_date). It never touches synthetic
bootstrap records, legacy pre-build1 records, or any entry it can't find a
clear match for -- those are left alone, not guessed at.

Usage:
    python3 tools/dedupe_truth_layer.py            # dry run, prints what it would do
    python3 tools/dedupe_truth_layer.py --apply     # writes changes, keeps a .bak
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRUTH_LAYER_JSON = "data/truth_layer/trade_history.json"


def _close_date(rec: dict) -> str:
    return str(rec.get("close_time") or "")[:10]  # date part only


def _match_key(rec: dict):
    return (
        str(rec.get("strategy") or "").upper(),
        round(float(rec.get("profit") or 0), 2),
        round(float(rec.get("lot") or 0), 3),
        _close_date(rec),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()

    if not os.path.exists(TRUTH_LAYER_JSON):
        print(f"[skip] {TRUTH_LAYER_JSON} not found")
        return

    with open(TRUTH_LAYER_JSON, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    records = [json.loads(l) for l in lines]

    by_key = defaultdict(list)
    for i, rec in enumerate(records):
        by_key[_match_key(rec)].append(i)

    to_remove = set()
    pairs_found = 0

    for key, idxs in by_key.items():
        authoritative = [
            i for i in idxs
            if (records[i].get("extra") or {}).get("source") == "mt5_history_sync"
            and records[i].get("build_id")
        ]
        bridge_dupes = [
            i for i in idxs
            if (records[i].get("extra") or {}).get("source") == "csv_truth_bridge"
            and not records[i].get("build_id")
        ]
        if authoritative and bridge_dupes:
            pairs_found += 1
            to_remove.update(bridge_dupes)

    print(f"BUILD_ID-tagged records total: {sum(1 for r in records if r.get('build_id'))}")
    print(f"Total records:                 {len(records)}")
    print(f"Duplicate pairs matched:        {pairs_found}")
    print(f"Bridge-duplicate rows to remove: {len(to_remove)}")

    if not to_remove:
        print("Nothing to clean up.")
        return

    kept = [r for i, r in enumerate(records) if i not in to_remove]
    removed = [r for i, r in enumerate(records) if i in to_remove]

    print("\nSample of rows that would be removed:")
    for r in removed[:5]:
        print(f"  ticket={r.get('ticket')} strategy={r.get('strategy')} profit={r.get('profit')} close_time={r.get('close_time')}")

    if not args.apply:
        print("\nDry run only -- pass --apply to write changes.")
        return

    shutil.copy2(TRUTH_LAYER_JSON, TRUTH_LAYER_JSON + ".dedupe.bak")
    with open(TRUTH_LAYER_JSON, "w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    quarantine_path = "data/truth_layer/trade_history_dedupe_removed.jsonl"
    with open(quarantine_path, "a", encoding="utf-8") as f:
        for rec in removed:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    print(f"\nRemoved {len(removed)} duplicate rows.")
    print(f"Backup of original: {TRUTH_LAYER_JSON}.dedupe.bak")
    print(f"Removed rows preserved for audit: {quarantine_path}")


if __name__ == "__main__":
    main()
