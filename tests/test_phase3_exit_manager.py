# =============================================================================
# FER3ON — PHASE 3 tests: exit manager (TP ladder / partials / trailing / time)
# =============================================================================
import os
import tempfile
import unittest

from core.exit_manager import (
    compute_tp_ladder,
    evaluate_exit,
    log_exit_action,
)

T0 = "2026-08-20T10:00:00+00:00"


def _candles(spec):
    return [{"time": f"2026-08-20T10:{i:02d}:00+00:00", "high": h, "low": l}
            for i, (h, l) in enumerate(spec, start=1)]


def _pos(**kw):
    base = {"direction": "BUY", "entry_price": 100.0, "sl_dist": 10.0,
            "open_time": T0, "strategy": "SMC"}
    base.update(kw)
    return base


class TestTPLadder(unittest.TestCase):
    def test_buy_ladder(self):
        # RR (1.2, 2.5, 4.0) × sl 10 → 112 / 125 / 140
        ladder = compute_tp_ladder("BUY", 100.0, 10.0)
        self.assertEqual([t["price"] for t in ladder], [112.0, 125.0, 140.0])
        self.assertEqual([t["fraction"] for t in ladder], [0.5, 0.3, 0.2])

    def test_sell_ladder_mirrored(self):
        ladder = compute_tp_ladder("SELL", 100.0, 10.0)
        self.assertEqual([t["price"] for t in ladder], [88.0, 75.0, 60.0])

    def test_bad_input(self):
        self.assertEqual(compute_tp_ladder("BUY", 0, 10.0), [])
        self.assertEqual(compute_tp_ladder(None, None, None), [])


class TestEvaluateExit(unittest.TestCase):
    def test_move_sl_breakeven_after_tp1(self):
        # bar hits high 116 >= TP1 112, low 99 > SL 90
        r = evaluate_exit(_pos(), _candles([(116, 99)]), atr=10.0)
        self.assertEqual(r["action"], "MOVE_SL_BREAKEVEN")
        self.assertEqual(r["tier"], 1)
        self.assertEqual(r["fraction"], 0.5)
        self.assertEqual(r["breakeven_buffer"], 1.0)  # 0.1 × ATR 10
        self.assertEqual(r["new_sl"], 101.0)

    def test_trail_after_tp2(self):
        r = evaluate_exit(_pos(), _candles([(126, 99)]), atr=10.0)
        self.assertEqual(r["action"], "TRAIL")
        self.assertEqual(r["tier"], 2)
        self.assertEqual(r["trail_dist"], 10.0)  # 1.0 × ATR

    def test_close_all_at_final_tp(self):
        r = evaluate_exit(_pos(), _candles([(141, 99)]), atr=10.0)
        self.assertEqual(r["action"], "CLOSE_ALL")
        self.assertEqual(r["tier"], 3)

    def test_sl_hit_beats_tp_same_bar(self):
        # conservative: same candle touches SL(90) and TP3(140) → SL_HIT
        r = evaluate_exit(_pos(), _candles([(141, 89)]), atr=10.0)
        self.assertEqual(r["action"], "SL_HIT")

    def test_time_exit(self):
        # 26 flat bars, never touches TP1(115) nor SL(90)
        r = evaluate_exit(_pos(), _candles([(110, 95)] * 26), atr=10.0)
        self.assertEqual(r["action"], "TIME_EXIT")
        self.assertEqual(r["bars_open"], 26)

    def test_none_when_trade_alive(self):
        r = evaluate_exit(_pos(), _candles([(110, 95)] * 5), atr=10.0)
        self.assertEqual(r["action"], "NONE")

    def test_sell_mirrored(self):
        r = evaluate_exit(_pos(direction="SELL"), _candles([(99, 84)]), atr=10.0)
        self.assertEqual(r["action"], "MOVE_SL_BREAKEVEN")  # low 84 <= TP1 85

    def test_never_raises_on_garbage(self):
        self.assertEqual(evaluate_exit(None, None)["action"], "INVALID")
        self.assertIn(evaluate_exit({"direction": "X"}, [])["action"], ("INVALID", "ERROR"))


class TestLedger(unittest.TestCase):
    def test_log_exit_action(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "exit.jsonl")
        self.assertTrue(log_exit_action({"action": "MOVE_SL_BREAKEVEN"}, log_path=path))
        self.assertTrue(os.path.exists(path))


class TestNoExecutionCapability(unittest.TestCase):
    def test_no_execution_imports(self):
        import core.exit_manager as mod
        with open(mod.__file__, encoding="utf-8") as fh:
            src = fh.read()
        for banned in ("MetaTrader5", "order_send"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
