import csv

import pytest

from testing.historical_data_audit import audit_candle_csv


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writerows(rows)


def test_audit_accepts_valid_ordered_candles(tmp_path):
    path = tmp_path / "candles.csv"
    _write_csv(path, [
        ["2026.01.01 00:00", 100, 102, 99, 101, 10],
        ["2026.01.01 00:05", 101, 103, 100, 102, 11],
        ["2026.01.01 00:15", 102, 103, 101, 102, 12],
    ])

    report = audit_candle_csv(str(path), timeframe_minutes=5)

    assert report["valid"] is True
    assert report["rows"] == 3
    assert report["gaps"] == 1
    assert report["largest_gap_minutes"] == 10
    assert report["first_timestamp"] == "2026-01-01 00:00:00"


def test_audit_rejects_invalid_ohlc_and_negative_volume(tmp_path):
    path = tmp_path / "invalid.csv"
    _write_csv(path, [
        ["2026.01.01 00:00", 100, 99, 98, 101, -1],
    ])

    report = audit_candle_csv(str(path), timeframe_minutes=5)

    assert report["valid"] is False
    assert report["invalid_ohlc_rows"] == 1
    assert report["invalid_volume_rows"] == 1


def test_audit_reports_duplicate_and_out_of_order_timestamps(tmp_path):
    path = tmp_path / "unordered.csv"
    _write_csv(path, [
        ["2026.01.01 00:05", 100, 102, 99, 101, 10],
        ["2026.01.01 00:05", 101, 103, 100, 102, 11],
        ["2026.01.01 00:00", 102, 103, 101, 102, 12],
    ])

    report = audit_candle_csv(str(path), timeframe_minutes=5)

    assert report["valid"] is False
    assert report["duplicate_timestamps"] == 1
    assert report["out_of_order_rows"] == 1


def test_audit_rejects_nonpositive_timeframe(tmp_path):
    path = tmp_path / "candles.csv"
    _write_csv(path, [])

    with pytest.raises(ValueError, match="timeframe_minutes"):
        audit_candle_csv(str(path), timeframe_minutes=0)


def test_audit_rejects_missing_columns(tmp_path):
    path = tmp_path / "candles.csv"
    path.write_text("Date;Open;High;Low\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        audit_candle_csv(str(path), timeframe_minutes=5)
