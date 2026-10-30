import os
import unittest

from testing.faie_backtest import (
    run_faie_backtest,
    _row_to_decision_context,
    FaieBacktestReport,
    MIN_ROWS_FOR_CONFIDENT_REPORT,
)


def _row(signal="BUY", strategy="SMC", result="WIN", profit="10.0", **kwargs):
    row = {
        "signal": signal,
        "strategy": strategy,
        "result": result,
        "profit": profit,
        "ticket": kwargs.pop("ticket", "1"),
        "date": kwargs.pop("date", "2026-01-01T00:00:00+00:00"),
        "market_regime": kwargs.pop("market_regime", "TRENDING"),
        "session": kwargs.pop("session", "LONDON"),
        "rr_ratio": kwargs.pop("rr_ratio", "2.0"),
        "quality_score": kwargs.pop("quality_score", "70.0"),
        "brain_score": kwargs.pop("brain_score", "65.0"),
    }
    row.update(kwargs)
    return row


class TestRowToDecisionContext(unittest.TestCase):
    def test_valid_row_produces_a_context(self):
        ctx = _row_to_decision_context(_row())
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.signal, "BUY")
        self.assertEqual(ctx.strategy, "SMC")

    def test_missing_signal_is_skipped(self):
        row = _row()
        row["signal"] = ""
        self.assertIsNone(_row_to_decision_context(row))

    def test_invalid_signal_value_is_skipped(self):
        row = _row(signal="CLOSE")
        self.assertIsNone(_row_to_decision_context(row))

    def test_missing_strategy_is_skipped(self):
        row = _row(strategy="")
        self.assertIsNone(_row_to_decision_context(row))

    def test_unknown_strategy_is_skipped(self):
        row = _row(strategy="UNKNOWN")
        self.assertIsNone(_row_to_decision_context(row))

    def test_malformed_numeric_field_does_not_raise(self):
        row = _row(rr_ratio="not_a_number")
        ctx = _row_to_decision_context(row)
        self.assertIsNotNone(ctx)  # falls back to DecisionContext's own default


class TestRunFaieBacktest(unittest.TestCase):
    def test_no_rows_returns_no_data_status(self):
        report = run_faie_backtest(history_rows=[])
        self.assertIsInstance(report, FaieBacktestReport)
        self.assertEqual(report.status, "NO_DATA")
        self.assertEqual(report.evaluated_rows, 0)

    def test_all_rows_skipped_returns_no_data_status(self):
        rows = [_row(strategy="") for _ in range(5)]
        report = run_faie_backtest(history_rows=rows)
        self.assertEqual(report.skipped_rows, 5)
        self.assertEqual(report.status, "NO_DATA")

    def test_small_sample_flagged_insufficient_data(self):
        rows = [_row(ticket=str(i)) for i in range(3)]
        report = run_faie_backtest(history_rows=rows)
        self.assertLess(report.evaluated_rows, MIN_ROWS_FOR_CONFIDENT_REPORT)
        self.assertEqual(report.status, "INSUFFICIENT_DATA")

    def test_agreement_rate_is_between_zero_and_one(self):
        rows = [_row(ticket=str(i), signal="BUY" if i % 2 == 0 else "SELL")
                for i in range(MIN_ROWS_FOR_CONFIDENT_REPORT + 5)]
        report = run_faie_backtest(history_rows=rows)
        self.assertGreaterEqual(report.agreement_rate, 0.0)
        self.assertLessEqual(report.agreement_rate, 1.0)
        self.assertEqual(
            report.agreements + report.opposite_disagreements + report.neutral_calls,
            report.evaluated_rows,
        )

    def test_open_trades_excluded_from_would_have_lists(self):
        rows = [_row(ticket=str(i), result="OPEN", profit="0.0")
                for i in range(MIN_ROWS_FOR_CONFIDENT_REPORT)]
        report = run_faie_backtest(history_rows=rows)
        self.assertEqual(len(report.would_have_avoided_losses), 0)
        self.assertEqual(len(report.would_have_missed_wins), 0)

    def test_mixed_skip_and_valid_rows_counted_correctly(self):
        rows = [_row(ticket=str(i)) for i in range(MIN_ROWS_FOR_CONFIDENT_REPORT)]
        rows += [_row(ticket="bad", strategy="") for _ in range(3)]
        report = run_faie_backtest(history_rows=rows)
        self.assertEqual(report.total_rows, MIN_ROWS_FOR_CONFIDENT_REPORT + 3)
        self.assertEqual(report.skipped_rows, 3)
        self.assertEqual(report.evaluated_rows, MIN_ROWS_FOR_CONFIDENT_REPORT)

    def test_disagreement_cases_capped_by_max_disagreement_cases(self):
        rows = [_row(ticket=str(i), signal="SELL") for i in range(50)]
        report = run_faie_backtest(history_rows=rows, max_disagreement_cases=5)
        self.assertLessEqual(len(report.disagreement_cases), 5)

    def test_never_raises_on_malformed_rows_mixed_with_good_ones(self):
        rows = [_row(ticket=str(i)) for i in range(MIN_ROWS_FOR_CONFIDENT_REPORT)]
        rows.append({"signal": "BUY", "strategy": "SMC"})  # missing everything else
        rows.append({})  # completely empty
        try:
            report = run_faie_backtest(history_rows=rows)
        except Exception as exc:  # pragma: no cover
            self.fail(f"run_faie_backtest raised unexpectedly: {exc}")
        self.assertIsInstance(report, FaieBacktestReport)

    def test_to_dict_is_json_shape(self):
        rows = [_row(ticket=str(i)) for i in range(MIN_ROWS_FOR_CONFIDENT_REPORT)]
        report = run_faie_backtest(history_rows=rows)
        d = report.to_dict()
        for key in (
            "total_rows", "skipped_rows", "evaluated_rows", "agreement_rate",
            "disagreement_cases", "would_have_avoided_losses",
            "would_have_missed_wins", "status", "note",
        ):
            self.assertIn(key, d)

    def test_default_csv_path_loads_real_history_file(self):
        # Integration smoke test against real repo data — proves the
        # csv_path/read_csv_records wiring works end-to-end, not just with
        # hand-built row dicts.
        #
        # data/history/trades.csv itself was intentionally reset to empty on
        # 2026-07-23 (see core/mt5_history_sync.py's close-logging fix and
        # data/history/archive/) -- it only had pre-fix rows with permanently
        # zeroed quality_score/rr_ratio/brain_score, which aren't meaningful
        # to backtest against. The archived pre-fix file is still a real,
        # on-disk CSV of the same shape, so it still exercises the same
        # wiring this test cares about.
        archived_path = os.path.join(
            os.path.dirname(__file__), "..",
            "data", "history", "archive", "trades_pre_sync_fix_2026-07-23.csv",
        )
        report = run_faie_backtest(csv_path=archived_path)
        self.assertGreater(report.total_rows, 0)
        self.assertIn(report.status, ("OK", "INSUFFICIENT_DATA", "NO_DATA"))


if __name__ == "__main__":
    unittest.main()
