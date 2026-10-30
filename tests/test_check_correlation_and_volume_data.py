import unittest
from unittest.mock import MagicMock

from tools.check_correlation_and_volume_data import find_candidate_symbols, check_volume_kind


def _symbol(name):
    s = MagicMock()
    s.name = name
    return s


class TestFindCandidateSymbols(unittest.TestCase):
    def test_finds_dxy_variant_by_pattern(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.symbols_get.return_value = [
            _symbol("USDX"), _symbol("EURUSD"), _symbol("XAUUSD"),
        ]
        mod.mt5 = fake_mt5
        found = find_candidate_symbols()
        self.assertIn("US Dollar Index (DXY)", found)
        self.assertIn("USDX", found["US Dollar Index (DXY)"])

    def test_no_symbols_available_returns_empty_dict(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.symbols_get.return_value = None
        mod.mt5 = fake_mt5
        self.assertEqual(find_candidate_symbols(), {})

    def test_no_matches_returns_empty_dict_not_error(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.symbols_get.return_value = [_symbol("EURUSD"), _symbol("XAUUSD")]
        mod.mt5 = fake_mt5
        self.assertEqual(find_candidate_symbols(), {})

    def test_matches_multiple_categories_independently(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.symbols_get.return_value = [
            _symbol("DXY"), _symbol("US500"), _symbol("US10Y"),
        ]
        mod.mt5 = fake_mt5
        found = find_candidate_symbols()
        self.assertIn("US Dollar Index (DXY)", found)
        self.assertIn("S&P 500 index", found)
        self.assertIn("US 10Y Treasury Yield", found)


class TestCheckVolumeKind(unittest.TestCase):
    def test_detects_real_volume_present(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.TIMEFRAME_M5 = 5
        fake_mt5.copy_rates_from_pos.return_value = [
            {"real_volume": 120, "tick_volume": 300},
            {"real_volume": 95, "tick_volume": 280},
        ]
        mod.mt5 = fake_mt5
        result = check_volume_kind("XAUUSD")
        self.assertTrue(result["has_real_volume"])
        self.assertEqual(result["nonzero_real_volume_bars"], 2)

    def test_detects_tick_volume_only(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.TIMEFRAME_M5 = 5
        fake_mt5.copy_rates_from_pos.return_value = [
            {"real_volume": 0, "tick_volume": 300},
            {"real_volume": 0, "tick_volume": 280},
        ]
        mod.mt5 = fake_mt5
        result = check_volume_kind("XAUUSD")
        self.assertFalse(result["has_real_volume"])
        self.assertIn("tick_volume only", result["note"])

    def test_no_rates_returned_reported_gracefully(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.TIMEFRAME_M5 = 5
        fake_mt5.copy_rates_from_pos.return_value = None
        mod.mt5 = fake_mt5
        result = check_volume_kind("BADSYMBOL")
        self.assertIsNone(result["has_real_volume"])
        self.assertEqual(result["bars_checked"], 0)

    def test_missing_real_volume_field_handled_gracefully(self):
        import tools.check_correlation_and_volume_data as mod
        fake_mt5 = MagicMock()
        fake_mt5.TIMEFRAME_M5 = 5
        fake_mt5.copy_rates_from_pos.return_value = [{"tick_volume": 100}]  # no real_volume key
        mod.mt5 = fake_mt5
        result = check_volume_kind("XAUUSD")
        self.assertIsNone(result["has_real_volume"])
        self.assertIn("no real_volume field", result["note"])


if __name__ == "__main__":
    unittest.main()
