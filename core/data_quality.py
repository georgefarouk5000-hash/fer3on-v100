"""Shared validation and quarantine for analytics ledgers."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

DATA_EPOCH = "2026-09-01-clean"
SCHEMA_VERSION = "5.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_trade_record(record: Dict[str, Any], *, require_rejection: bool = False) -> Tuple[bool, str]:
    if not isinstance(record, dict):
        return False, "NOT_OBJECT"
    direction = str(record.get("direction") or "").upper()
    if direction not in {"BUY", "SELL"}:
        return False, "INVALID_DIRECTION"
    try:
        if float(record.get("entry_price") or 0) <= 0:
            return False, "INVALID_ENTRY_PRICE"
        if float(record.get("sl_dist") or 0) <= 0:
            return False, "INVALID_SL_DISTANCE"
        if float(record.get("tp_dist") or 0) <= 0:
            return False, "INVALID_TP_DISTANCE"
    except (TypeError, ValueError):
        return False, "NON_NUMERIC_TRADE_LEVEL"
    if not record.get("signal_time"):
        return False, "MISSING_SIGNAL_TIME"
    if require_rejection and not str(record.get("reject_reason") or "").strip():
        return False, "MISSING_REJECTION_REASON"
    return True, "OK"


def quarantine(record: Any, reason: str, path: str) -> bool:
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload = {
            "record_type": "QUARANTINED_INVALID",
            "data_epoch": DATA_EPOCH,
            "schema_version": SCHEMA_VERSION,
            "quarantine_reason": reason,
            "quarantined_at": _now(),
            "record": record,
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def stamp(record: Dict[str, Any]) -> Dict[str, Any]:
    record.setdefault("data_epoch", DATA_EPOCH)
    record.setdefault("schema_version", SCHEMA_VERSION)
    return record


def count_records(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except Exception:
        return 0


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
    except Exception:
        return
