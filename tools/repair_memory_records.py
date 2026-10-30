from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.data_integrity import AI_MEMORY_COLUMNS, AI_MEMORY_FILE, dump_rows, read_csv_records
from core.trade_identity import magic_from_strategy


def session_from_hour(hour):
    try:
        hour = int(float(hour))
    except Exception:
        return "UNKNOWN"
    if 0 <= hour < 8:
        return "ASIA"
    if 8 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 18:
        return "NEWYORK"
    return "OFF_HOURS"


def main() -> None:
    rows = read_csv_records(AI_MEMORY_FILE, AI_MEMORY_COLUMNS)
    updated = 0
    for row in rows:
        strategy = str(row.get("strategy", "UNKNOWN") or "UNKNOWN").upper()
        if str(row.get("magic", "") or "").strip() in {"", "0"}:
            magic = magic_from_strategy(strategy, fallback=0)
            if magic:
                row["magic"] = magic
                updated += 1
        session = str(row.get("session", "") or "").upper()
        if session in {"", "UNKNOWN"}:
            inferred = session_from_hour(row.get("hour", 0))
            if inferred != "UNKNOWN":
                row["session"] = inferred
                updated += 1
        if str(row.get("confidence_score", "") or "").strip() == "" and str(row.get("confidence_pct", "") or "").strip() != "":
            row["confidence_score"] = row.get("confidence_pct", 0)
            updated += 1
    dump_rows(AI_MEMORY_FILE, AI_MEMORY_COLUMNS, rows)
    print({"rows": len(rows), "updated_fields": updated})


if __name__ == "__main__":
    main()
