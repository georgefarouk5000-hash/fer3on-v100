import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from analytics.execution_quality import (
    record_execution_outcome,
    summarize_execution_quality,
    ExecutionQualitySummary,
)


class TestRecordExecutionOutcome(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self._tmpdir.name, "execution_quality.csv")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_creates_csv_with_header_on_first_write(self):
        ok = record_execution_outcome(
            ticket=1001,
            requested_price=2350.10,
            filled_price=2350.14,
            requested_time=datetime.now(timezone.utc),
            filled_time=datetime.now(timezone.utc),
            rejected=False,
            symbol="XAUUSD",
            csv_path=self.csv_path,
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(self.csv_path))
        with open(self.csv_path, "r", encoding="utf-8") as fh:
            header = fh.readline().strip()
        self.assertIn("slippage", header)
        self.assertIn("rejected", header)

    def test_computes_slippage_and_delay_for_a_fill(self):
        t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=0.35)
        record_execution_outcome(
            ticket=2002,
            requested_price=100.00,
            filled_price=100.05,
            requested_time=t0,
            filled_time=t1,
            rejected=False,
            symbol="XAUUSD",
            csv_path=self.csv_path,
        )
        summary = summarize_execution_quality(csv_path=self.csv_path)
        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.rejections, 0)
        self.assertAlmostEqual(summary.avg_slippage, 0.05, places=4)
        self.assertAlmostEqual(summary.avg_delay_seconds, 0.35, places=4)

    def test_rejected_order_excluded_from_slippage_and_delay(self):
        record_execution_outcome(
            ticket=None,
            requested_price=100.00,
            filled_price=None,
            requested_time=datetime.now(timezone.utc),
            filled_time=None,
            rejected=True,
            symbol="XAUUSD",
            csv_path=self.csv_path,
        )
        summary = summarize_execution_quality(csv_path=self.csv_path)
        self.assertEqual(summary.total_records, 1)
        self.assertEqual(summary.rejections, 1)
        self.assertEqual(summary.fills, 0)
        self.assertIsNone(summary.avg_slippage)
        self.assertIsNone(summary.avg_delay_seconds)
        self.assertEqual(summary.rejection_rate, 1.0)

    def test_never_raises_on_unwritable_path(self):
        bad_parent = os.path.join(self._tmpdir.name, "not_a_dir")
        with open(bad_parent, "w", encoding="utf-8") as fh:
            fh.write("i am a file")
        bad_path = os.path.join(bad_parent, "execution_quality.csv")
        ok = record_execution_outcome(
            ticket=1,
            requested_price=1.0,
            filled_price=1.0,
            requested_time=datetime.now(timezone.utc),
            filled_time=datetime.now(timezone.utc),
            rejected=False,
            csv_path=bad_path,
        )
        self.assertFalse(ok)


class TestSummarizeExecutionQuality(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self._tmpdir.name, "execution_quality.csv")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_records_returns_insufficient_note_not_zero_rates(self):
        summary = summarize_execution_quality(csv_path=self.csv_path)
        self.assertIsInstance(summary, ExecutionQualitySummary)
        self.assertEqual(summary.total_records, 0)
        self.assertEqual(summary.coverage_note, "NO_RECORDS")

    def test_mixed_fills_and_rejections_rejection_rate(self):
        t0 = datetime.now(timezone.utc)
        for i in range(3):
            record_execution_outcome(
                ticket=i, requested_price=100.0, filled_price=100.1,
                requested_time=t0, filled_time=t0 + timedelta(seconds=0.1),
                rejected=False, csv_path=self.csv_path,
            )
        for i in range(1):
            record_execution_outcome(
                ticket=None, requested_price=100.0, filled_price=None,
                requested_time=t0, filled_time=None,
                rejected=True, csv_path=self.csv_path,
            )
        summary = summarize_execution_quality(csv_path=self.csv_path)
        self.assertEqual(summary.total_records, 4)
        self.assertEqual(summary.fills, 3)
        self.assertEqual(summary.rejections, 1)
        self.assertAlmostEqual(summary.rejection_rate, 0.25, places=4)

    def test_missing_slippage_field_excluded_not_zeroed(self):
        # A fill with no requested_price recorded (broker didn't echo one)
        # must not silently contribute a slippage of 0.0.
        record_execution_outcome(
            ticket=5, requested_price=None, filled_price=100.2,
            requested_time=datetime.now(timezone.utc),
            filled_time=datetime.now(timezone.utc),
            rejected=False, csv_path=self.csv_path,
        )
        summary = summarize_execution_quality(csv_path=self.csv_path)
        self.assertEqual(summary.fills, 1)
        self.assertEqual(summary.slippage_sample_size, 0)
        self.assertIsNone(summary.avg_slippage)
        self.assertNotEqual(summary.coverage_note, "")


if __name__ == "__main__":
    unittest.main()
