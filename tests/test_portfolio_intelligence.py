import unittest

from analytics.portfolio_intelligence import assess_correlated_exposure, PortfolioRiskNote


def _trade(direction, risk_percent=1.0, symbol=None, meta=None):
    d = {"direction": direction, "risk_percent": risk_percent}
    if symbol:
        d["symbol"] = symbol
    if meta:
        d["meta"] = meta
    return d


class TestAssessCorrelatedExposure(unittest.TestCase):
    def test_empty_open_trades_returns_no_conflict_note_not_error(self):
        result = assess_correlated_exposure([])
        self.assertIsInstance(result, PortfolioRiskNote)
        self.assertEqual(result.same_direction_count, 0)
        self.assertIn("no correlated exposure", result.note)

    def test_single_open_trade_is_not_flagged_as_correlated(self):
        result = assess_correlated_exposure([_trade("BUY", symbol="XAUUSD")])
        self.assertEqual(result.same_direction_count, 1)
        self.assertIn("no correlated exposure", result.note)

    def test_multiple_same_direction_trades_are_flagged(self):
        trades = [
            _trade("BUY", symbol="XAUUSD"),
            _trade("BUY", symbol="XAUUSD"),
            _trade("BUY", symbol="XAUUSD"),
        ]
        result = assess_correlated_exposure(trades)
        self.assertEqual(result.same_direction_count, 3)
        self.assertEqual(result.dominant_direction, "BUY")
        self.assertIn("XAUUSD", result.same_direction_symbols)
        self.assertIn("diversification, not conflict", result.note)

    def test_does_not_block_or_resize_only_reports(self):
        trades = [_trade("BUY", symbol="XAUUSD") for _ in range(5)]
        result = assess_correlated_exposure(trades)
        # The note must be informational only — no attribute on the
        # dataclass represents a block/resize action of any kind.
        forbidden_attrs = ("blocked", "resized", "max_lot", "action")
        for attr in forbidden_attrs:
            self.assertFalse(hasattr(result, attr))

    def test_net_directional_exposure_nets_opposite_directions(self):
        trades = [
            _trade("BUY", risk_percent=1.0, symbol="XAUUSD"),
            _trade("SELL", risk_percent=0.4, symbol="EURUSD"),
        ]
        result = assess_correlated_exposure(trades)
        self.assertAlmostEqual(result.net_directional_exposure, 0.6, places=4)

    def test_symbol_pulled_from_meta_when_no_top_level_symbol(self):
        trades = [
            _trade("BUY", meta={"symbol": "GBPUSD"}),
            _trade("BUY", meta={"symbol": "GBPUSD"}),
        ]
        result = assess_correlated_exposure(trades)
        self.assertIn("GBPUSD", result.same_direction_symbols)

    def test_missing_symbol_falls_back_to_unknown_not_error(self):
        trades = [_trade("BUY"), _trade("BUY")]
        result = assess_correlated_exposure(trades)
        self.assertEqual(result.same_direction_symbols, ["UNKNOWN"])

    def test_malformed_risk_percent_does_not_raise(self):
        trades = [
            {"direction": "BUY", "risk_percent": "not_a_number", "symbol": "XAUUSD"},
            _trade("BUY", symbol="XAUUSD"),
        ]
        result = assess_correlated_exposure(trades)
        self.assertEqual(result.same_direction_count, 2)

    def test_to_dict_is_json_serializable_shape(self):
        result = assess_correlated_exposure([_trade("BUY", symbol="XAUUSD")])
        d = result.to_dict()
        self.assertIn("same_direction_count", d)
        self.assertIn("net_directional_exposure", d)
        self.assertIn("note", d)


if __name__ == "__main__":
    unittest.main()
