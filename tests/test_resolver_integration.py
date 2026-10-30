import json
import tempfile
import unittest
from pathlib import Path

from analytics.shadow_counterfactual import resolve_outcomes, summary


class ResolverIntegrationTests(unittest.TestCase):
    def _ledger(self, records):
        root = Path(tempfile.mkdtemp(prefix="fer3on-resolver-test-"))
        path = root / "rejected_shadow.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def _record(self, signal_id, direction, entry, sl, tp, signal_time="2026-09-07T00:00:00+00:00"):
        return {
            "signal_id": signal_id,
            "direction": direction,
            "entry_price": entry,
            "sl_dist": sl,
            "tp_dist": tp,
            "signal_time": signal_time,
            "outcome": "PENDING",
        }

    def test_resolves_win_loss_and_timeout(self):
        path = self._ledger([
            self._record("win", "BUY", 100.0, 2.0, 2.0),
            self._record("loss", "SELL", 100.0, 2.0, 2.0),
            self._record("timeout", "BUY", 100.0, 20.0, 20.0),
        ])
        candles = [
            {"time": "2026-09-07T00:05:00+00:00", "high": 103.0, "low": 99.0},
            {"time": "2026-09-07T00:10:00+00:00", "high": 101.0, "low": 99.0},
        ]
        result = resolve_outcomes(candles, log_path=str(path), horizon=2)
        self.assertEqual(result["resolved"], 3)
        stats = summary(log_path=str(path))
        self.assertEqual(stats["WIN"], 1)
        self.assertEqual(stats["LOSS"], 1)
        self.assertEqual(stats["TIMEOUT"], 1)

    def test_invalid_record_remains_pending(self):
        path = self._ledger([self._record("invalid", "BUY", 0.0, 2.0, 2.0)])
        result = resolve_outcomes(
            [{"time": "2026-09-07T00:05:00+00:00", "high": 103.0, "low": 99.0}],
            log_path=str(path),
        )
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(summary(log_path=str(path))["pending"], 1)


if __name__ == "__main__":
    unittest.main()
