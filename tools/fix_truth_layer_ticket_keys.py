"""
Retroactive migration: fix the `ticket` field on truth_layer records that
were written BEFORE the ticket-key fix shipped (core/mt5_history_sync.py
used to key TradeRecord by deal.ticket instead of close_ticket/position_id
-- see that fix's comment for the full writeup).

Why this is needed in addition to that code fix: correcting the CODE only
stops the bug for trades closed *after* the fix is running. Every record
already sitting in data/truth_layer/trade_history.json still has the old,
wrong ticket value. Since analytics/csv_truth_bridge.py::sync_csv_to_truth_layer()
dedupes against trades.csv by comparing ticket values, it still can't find
those old records under trades.csv's ticket (=close_ticket) -- so it still
creates a fresh duplicate on every run, and because build_id now correctly
propagates through the bridge (also fixed), that duplicate carries a valid
build_id and DOES count toward analytics/quant_engine.py's filtered sample
size. Observed live: SMC sample size doubled from 17 (honest) to 34
(17 real + 17 fresh duplicates) the first time جو ran the fixed code
against the previously-shipped data.

This migration corrects the ROOT data, so the bridge's own ticket-based
dedup starts working correctly and stops creating new duplicates going
forward. It does not remove anything -- see tools/dedupe_truth_layer.py
for cleaning up duplicates that have already been created.

Matches each mt5_history_sync-sourced truth_layer record (no existing
extra.deal_ticket -- i.e. written before the fix) against its trades.csv
row by (strategy, profit, lot, close_date), and replaces `ticket` with
that row's ticket (= close_ticket), same as trades.csv.

Usage:
    python3 tools/fix_truth_layer_ticket_keys.py            # dry run
    python3 tools/fix_truth_layer_ticket_keys.py --apply     # writes changes
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import BUILD_ID  # noqa: E402

TRUTH_LAYER_JSON = "data/truth_layer/trade_history.json"
TRADES_CSV = "data/history/trades.csv"


def _close_date(value: str) -> str:
    return str(value or "")[:10]


def _match_key(strategy, profit, close_date):
    return (str(strategy or "").upper(), round(float(profit or 0), 2), close_date)


def _pick_best_candidate(candidates, target_lot):
    if len(candidates) == 1:
        return candidates[0]
    target_lot = round(float(target_lot or 0), 3)
    return min(candidates, key=lambda r: abs(round(float(r.get("lot") or 0), 3) - target_lot))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(TRUTH_LAYER_JSON) or not os.path.exists(TRADES_CSV):
        print("[skip] required files not found")
        return

    with open(TRADES_CSV, newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    csv_by_key = {}
    csv_by_loose_key = {}
    for row in csv_rows:
        if row.get("result") == "OPEN":
            continue
        key = _match_key(row.get("strategy"), row.get("profit"), _close_date(row.get("date")))
        csv_by_key.setdefault(key, []).append(row)
        loose_key = (str(row.get("strategy") or "").upper(), round(float(row.get("profit") or 0), 2))
        csv_by_loose_key.setdefault(loose_key, []).append(row)

    with open(TRUTH_LAYER_JSON, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    records = [json.loads(l) for l in lines]

    fixed = 0
    used_tickets = set()
    for rec in records:
        if rec.get("build_id") != BUILD_ID:
            continue  # never touch legacy/synthetic records, even on a profit coincidence
        if (rec.get("extra") or {}).get("source") != "mt5_history_sync":
            continue
        if (rec.get("extra") or {}).get("deal_ticket"):
            continue  # already written by the fixed code -- ticket is already correct
        key = _match_key(rec.get("strategy"), rec.get("profit"), _close_date(rec.get("close_time")))
        candidates = [c for c in (csv_by_key.get(key) or []) if int(c["ticket"]) not in used_tickets]
        if not candidates:
            # Fallback: date can differ by a few hours between trades.csv's
            # "date" (written when the sync cycle upserted the row) and
            # truth_layer's close_time (the deal's actual close timestamp)
            # near a UTC day boundary. Only accept this if it's unambiguous.
            loose_key = (str(rec.get("strategy") or "").upper(), round(float(rec.get("profit") or 0), 2))
            loose_candidates = [c for c in (csv_by_loose_key.get(loose_key) or []) if int(c["ticket"]) not in used_tickets]
            if len(loose_candidates) == 1:
                candidates = loose_candidates
        if not candidates:
            continue
        best = _pick_best_candidate(candidates, rec.get("lot"))
        correct_ticket = int(best["ticket"])
        used_tickets.add(correct_ticket)
        if rec.get("ticket") != correct_ticket:
            print(f"  ticket {rec.get('ticket')} -> {correct_ticket} (strategy={rec.get('strategy')} profit={rec.get('profit')})")
            rec["extra"] = dict(rec.get("extra") or {})
            rec["extra"]["deal_ticket"] = rec.get("ticket")  # preserve the old (wrong-for-this-purpose) value
            rec["ticket"] = correct_ticket
            fixed += 1

    print(f"\n{fixed} record(s) would be corrected." if not args.apply else f"\n{fixed} record(s) corrected.")

    if not args.apply or fixed == 0:
        if fixed == 0:
            print("Nothing to fix.")
        else:
            print("Dry run only -- pass --apply to write changes.")
        return

    shutil.copy2(TRUTH_LAYER_JSON, TRUTH_LAYER_JSON + ".ticketfix.bak")
    with open(TRUTH_LAYER_JSON, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"Backup saved: {TRUTH_LAYER_JSON}.ticketfix.bak")


if __name__ == "__main__":
    main()
