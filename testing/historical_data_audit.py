"""Streaming validation for historical OHLCV CSV files."""

from __future__ import annotations

import csv
import argparse
import json
import math
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, Optional


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close")
DATASET_FILES = {
    "XAU_1m_data.csv": 1,
    "XAU_5m_data.csv": 5,
    "XAU_15m_data.csv": 15,
    "XAU_30m_data.csv": 30,
    "XAU_1h_data.csv": 60,
    "XAU_4h_data.csv": 240,
    "XAU_1d_data.csv": 1440,
    "XAU_1w_data.csv": 10080,
    "XAU_1Month_data.csv": 43200,
}


def audit_candle_csv(path: str, timeframe_minutes: int) -> Dict[str, Any]:
    """Validate a semicolon-separated candle CSV without retaining its rows."""
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be positive")

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Historical candle file not found: {source}")

    row_count = 0
    malformed_rows = 0
    invalid_ohlc_rows = 0
    invalid_volume_rows = 0
    duplicate_timestamps = 0
    out_of_order_rows = 0
    gap_count = 0
    largest_gap_minutes = 0
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    first_errors = []

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        columns = {
            str(column or "").strip().lower(): column
            for column in (reader.fieldnames or [])
        }
        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        if missing:
            raise ValueError(
                f"{source}: missing columns {missing}; found {reader.fieldnames}"
            )

        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            try:
                raw_timestamp = str(row[columns["date"]]).strip()
                timestamp = datetime.fromisoformat(raw_timestamp.replace(".", "-", 2))
                prices = {
                    name: float(row[columns[name]])
                    for name in ("open", "high", "low", "close")
                }
                volume_column = columns.get("volume")
                volume = (
                    float(row[volume_column])
                    if volume_column and row.get(volume_column, "").strip()
                    else None
                )
                if any(not math.isfinite(value) for value in prices.values()):
                    raise ValueError("non-finite OHLC price")
                if volume is not None and not math.isfinite(volume):
                    raise ValueError("non-finite volume")
            except (KeyError, TypeError, ValueError) as exc:
                malformed_rows += 1
                if len(first_errors) < 20:
                    first_errors.append({"line": line_number, "error": str(exc)})
                continue

            if first_timestamp is None:
                first_timestamp = timestamp
            if last_timestamp is not None:
                delta_minutes = int((timestamp - last_timestamp).total_seconds() // 60)
                if delta_minutes == 0:
                    duplicate_timestamps += 1
                elif delta_minutes < 0:
                    out_of_order_rows += 1
                else:
                    expected_minutes = timeframe_minutes
                    if delta_minutes > expected_minutes:
                        gap_count += 1
                        largest_gap_minutes = max(largest_gap_minutes, delta_minutes)

            if (
                prices["low"] <= 0
                or prices["high"] < prices["low"]
                or prices["high"] < max(prices["open"], prices["close"])
                or prices["low"] > min(prices["open"], prices["close"])
            ):
                invalid_ohlc_rows += 1

            if volume is not None and volume < 0:
                invalid_volume_rows += 1

            last_timestamp = timestamp

    return {
        "path": str(source),
        "timeframe_minutes": timeframe_minutes,
        "rows": row_count,
        "malformed_rows": malformed_rows,
        "invalid_ohlc_rows": invalid_ohlc_rows,
        "invalid_volume_rows": invalid_volume_rows,
        "duplicate_timestamps": duplicate_timestamps,
        "out_of_order_rows": out_of_order_rows,
        "gaps": gap_count,
        "largest_gap_minutes": largest_gap_minutes,
        "first_timestamp": first_timestamp.isoformat(sep=" ") if first_timestamp else None,
        "last_timestamp": last_timestamp.isoformat(sep=" ") if last_timestamp else None,
        "errors": first_errors,
        "valid": (
            row_count > 0
            and malformed_rows == 0
            and invalid_ohlc_rows == 0
            and invalid_volume_rows == 0
            and duplicate_timestamps == 0
            and out_of_order_rows == 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate candle CSV ordering and OHLCV integrity."
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path("data") / "market_data" / "XAUUSD_all_timeframes_2004-2026"),
        help="Directory containing the extracted XAU candle CSV files.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    reports = []
    for filename, timeframe_minutes in DATASET_FILES.items():
        reports.append(
            audit_candle_csv(str(data_dir / filename), timeframe_minutes)
        )

    print(json.dumps(reports, indent=2, ensure_ascii=False))
    return 0 if all(report["valid"] for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
