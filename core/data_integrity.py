import csv
import os
from copy import deepcopy
from datetime import datetime, timezone

AI_MEMORY_FILE = "data/memory/ai_memory.csv"
HISTORY_FILE = "data/history/trades.csv"

AI_MEMORY_COLUMNS = [
    "date",
    "ticket",
    "strategy",
    "signal",
    "result",
    "profit",
    "atr",
    "market_regime",
    "hour",
    "spread",
    "session",
    "quality_score",
    "confidence_score",
    "confidence_pct",
    "exec_grade",
    "rr_ratio",
    "choch_state",
    "choch_strength",
    "liq_map_score",
    "liq_map_dir",
    "mtf_strength",
    "mtf_structural",
    "entry_price",
    "exit_price",
    "sl_dist",
    "tp_dist",
    "tp_tiers",
    "magic",
    "volume",
    "brain_score",
    "master_score",
    "dna_score",
    "history_score",
    "knowledge_score",
    "news_score",
    "decision_reason",
    "entry_reason",
    "entry_conditions",
    "conflict_report",
    "master_breakdown",
    "decision_snapshot_id",
    "decision_id",
    "account_id",
]

HISTORY_COLUMNS = [
    "date",
    "ticket",
    "signal",
    "lot",
    "profit",
    "result",
    "strategy",
    "session",
    "market_regime",
    "exec_grade",
    "rr_ratio",
    "quality_score",
    "brain_score",
    "build_id",
    "decision_id",
    "entry_reason",
    "entry_conditions",
    "entry_cost_complete",
    "entry_price",
    "stop_price",
    "target_price",
    "sl_dist",
    "tp_dist",
    "stop_source",
    "stop_anchor_price",
    "stop_anchor_index",
    "stop_anchor_label",
    "stop_reason",
    "stop_buffer",
    "account_id",
]

FIELD_ALIASES = {
    "date": "date",
    "datetime": "date",
    "trade_date": "date",
    "ticket": "ticket",
    "trade_number": "ticket",
    "trade_id": "ticket",
    "signal": "signal",
    "lot": "lot",
    "volume": "volume",
    "profit": "profit",
    "result": "result",
    "atr": "atr",
    "market_regime": "market_regime",
    "regime": "market_regime",
    "hour": "hour",
    "spread": "spread",
    "spread_pts": "spread",
    "session": "session",
    "strategy": "strategy",
    "quality": "quality_score",
    "quality_score": "quality_score",
    "confidence": "confidence_score",
    "confidence_score": "confidence_score",
    "confidence_pct": "confidence_pct",
    "exec_grade": "exec_grade",
    "rr_ratio": "rr_ratio",
    "choch_state": "choch_state",
    "choch_strength": "choch_strength",
    "liq_map_score": "liq_map_score",
    "liq_map_dir": "liq_map_dir",
    "mtf_strength": "mtf_strength",
    "mtf_structural": "mtf_structural",
    "entry_price": "entry_price",
    "exit_price": "exit_price",
    "sl_dist": "sl_dist",
    "tp_dist": "tp_dist",
    "tp_tiers": "tp_tiers",
    "magic": "magic",
    "brain_score": "brain_score",
    "master_score": "master_score",
    "dna_score": "dna_score",
    "history_score": "history_score",
    "knowledge_score": "knowledge_score",
    "news_score": "news_score",
    "decision_reason": "decision_reason",
    "entry_reason": "entry_reason",
    "entry_conditions": "entry_conditions",
    "conflict_report": "conflict_report",
    "master_breakdown": "master_breakdown",
    "decision_snapshot_id": "decision_snapshot_id",
    "decision_id": "decision_id",
    "entry_cost_complete": "entry_cost_complete",
    "entry_price": "entry_price",
    "stop_price": "stop_price",
    "target_price": "target_price",
    "sl_dist": "sl_dist",
    "tp_dist": "tp_dist",
    "stop_source": "stop_source",
    "stop_anchor_price": "stop_anchor_price",
    "stop_anchor_index": "stop_anchor_index",
    "stop_anchor_label": "stop_anchor_label",
    "stop_reason": "stop_reason",
    "stop_buffer": "stop_buffer",
    "build_id": "build_id",
    "account_id": "account_id",
}


def _canon(name):
    return str(name or "").strip().lower().replace(" ", "_")


def get_session_from_hour(hour):
    try:
        hour = int(hour)
    except Exception:
        return "UNKNOWN"
    if 0 <= hour < 8:
        return "ASIA"
    if 8 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 18:
        return "NEWYORK"
    return "OFF_HOURS"


def normalize_row(row):
    normalized = {}
    for key, value in (row or {}).items():
        canon = FIELD_ALIASES.get(_canon(key), _canon(key))
        normalized[canon] = value

    if not normalized.get("date"):
        normalized["date"] = datetime.now(timezone.utc).isoformat()

    if not normalized.get("session"):
        normalized["session"] = get_session_from_hour(normalized.get("hour", 0))

    if not normalized.get("result"):
        try:
            profit = float(normalized.get("profit", 0) or 0)
            normalized["result"] = "WIN" if profit >= 0 else "LOSS"
        except Exception:
            normalized["result"] = "UNKNOWN"

    for numeric_key, default in {
        "profit": 0,
        "atr": 0,
        "hour": 0,
        "spread": 0,
        "quality_score": 0,
        "confidence_score": 0,
        "confidence_pct": 0,
        "rr_ratio": 0,
        "liq_map_score": 0,
        "mtf_strength": 0,
        "entry_price": 0,
        "exit_price": 0,
        "sl_dist": 0,
        "tp_dist": 0,
        "brain_score": 0,
        "master_score": 0,
        "dna_score": 0,
        "history_score": 0,
        "knowledge_score": 0,
        "news_score": 0,
        "lot": 0,
        "volume": 0,
    }.items():
        value = normalized.get(numeric_key, default)
        if value in (None, ""):
            normalized[numeric_key] = default

    return normalized


def _ordered_row(row, columns):
    clean = normalize_row(row)
    return {col: clean.get(col, "") for col in columns}


def read_csv_records(path, columns=None):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return []

    normalized_rows = []
    for row in rows:
        clean = normalize_row(row)
        if columns:
            clean = {col: clean.get(col, "") for col in columns}
        normalized_rows.append(clean)
    return normalized_rows


def ensure_csv_schema(path, columns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
        return

    rows = read_csv_records(path)
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            current_header = csv.DictReader(f).fieldnames or []
    except Exception:
        current_header = []

    current_canon = [_canon(h) for h in current_header]
    target_canon = [_canon(h) for h in columns]
    if current_canon == target_canon:
        return

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(_ordered_row(row, columns))


def append_csv_row(path, columns, row):
    ensure_csv_schema(path, columns)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writerow(_ordered_row(row, columns))


def count_csv_rows(path):
    return len(read_csv_records(path))


def dump_rows(path, columns, rows):
    ensure_csv_schema(path, columns)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(_ordered_row(row, columns))


def find_csv_row(path, columns, key_column, key_value):
    """Return the first row (normalized dict) where str(row[key_column]) ==
    str(key_value), or None if no such row exists."""
    key_value = str(key_value)
    for row in read_csv_records(path, columns):
        if str(row.get(key_column, "")) == key_value:
            return row
    return None


def upsert_csv_row(path, columns, key_column, key_value, updates):
    """Merge `updates` into the first existing row where row[key_column] ==
    key_value (preserving every other field already on that row), or append a
    brand-new row built from `updates` if no matching row exists yet.

    Returns True if an existing row was updated in place, False if a new row
    was appended.

    This exists specifically so that closing a trade never has to blow away
    the rich open-time snapshot (quality_score, rr_ratio, brain_score,
    session, ...) just to record the final result/profit — see
    core/mt5_history_sync.py.
    """
    ensure_csv_schema(path, columns)
    rows = read_csv_records(path, columns)
    key_value = str(key_value)
    for row in rows:
        if str(row.get(key_column, "")) == key_value:
            row.update(updates)
            dump_rows(path, columns, rows)
            return True
    append_csv_row(path, columns, updates)
    return False
