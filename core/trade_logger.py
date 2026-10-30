import os
from datetime import datetime, timezone

from core.data_integrity import (
    HISTORY_COLUMNS,
    HISTORY_FILE,
    append_csv_row,
    ensure_csv_schema,
)
from core.settings import BUILD_ID
from core.account_scope import get_cached_account_id

CSV_FILE = HISTORY_FILE


def initialize_logger():
    ensure_csv_schema(CSV_FILE, HISTORY_COLUMNS)


def log_trade(trade_number, signal, lot, profit, **extra):
    initialize_logger()

    # DATA-INTEGRITY GUARD: trades.csv was found to contain 57 rows with a
    # blank ticket and blank strategy (real profit values, but no way to
    # trace them to an actual position or build). Root cause was a one-off
    # data-merge artifact, not a live call site in this build -- but this
    # function is the single write path for every HISTORY_FILE row, so it's
    # the right place to make that class of row impossible going forward
    # rather than trusting every future caller to always pass both fields.
    if not trade_number:
        raise ValueError(
            "log_trade: trade_number (ticket) is required — refusing to "
            "write an untraceable row to trades.csv"
        )
    if not extra.get("strategy"):
        raise ValueError(
            "log_trade: strategy is required — refusing to write a row to "
            "trades.csv with no strategy tag"
        )

    profit = round(float(profit or 0), 2)
    row = {
        "date": extra.get("date", datetime.now(timezone.utc).isoformat()),
        "ticket": trade_number,
        "signal": signal,
        "lot": lot,
        "profit": profit,
        "result": extra.get("result") or ("LOSS" if profit < 0 else "WIN"),
        "build_id": BUILD_ID,
        "account_id": get_cached_account_id(),
        **extra,
    }
    append_csv_row(CSV_FILE, HISTORY_COLUMNS, row)
    return row
