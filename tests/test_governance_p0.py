import unittest

import core.settings as settings
from core.risk_policy import get_risk_policy, validate_risk_policy
from core.data_source_registry import DATA_SOURCE_REGISTRY, resolve_data_source


class GovernanceP0Tests(unittest.TestCase):
    def test_risk_policy_is_single_source_of_truth(self):
        policy = get_risk_policy()
        self.assertIn("max_daily_risk_pct", policy)
        self.assertEqual(policy["max_daily_risk_pct"], settings.MAX_RISK_PER_DAY_PERCENT)
        self.assertEqual(policy["max_daily_loss_usd"], settings.MAX_DAILY_LOSS_USD)
        self.assertEqual(policy["max_daily_risk_pct"], settings.MAX_RISK_PER_DAY_PERCENT)
        self.assertTrue(validate_risk_policy(policy))

    def test_risk_policy_matches_settings_numeric_fields(self):
        # AUDIT FIX: the test above only ever checked max_daily_risk_pct,
        # so core/risk_policy.py's max_daily_trades silently drifted to 80
        # while settings.MAX_DAILY_TRADES stayed at 50 with nothing to catch
        # it. Cover every numeric field risk_policy.py claims to mirror from
        # settings.py so this class of drift fails CI instead of sitting
        # silently in an orphaned module.
        policy = get_risk_policy()
        self.assertEqual(policy["max_daily_trades"], settings.MAX_DAILY_TRADES)
        self.assertEqual(policy["max_open_trades"], settings.MAX_OPEN_TRADES)
        self.assertEqual(policy["max_lot"], settings.MAX_LOT)
        self.assertEqual(policy["min_lot"], settings.MIN_LOT)
        self.assertEqual(policy["max_sl_distance_dollars"], settings.MAX_SL_DISTANCE_DOLLARS)
        self.assertEqual(policy["cooldown_after_loss_sec"], settings.LOSS_PAUSE_COOLDOWN_SEC)
        self.assertEqual(policy["loss_pause_trigger"], settings.LOSS_PAUSE_TRIGGER)
        self.assertEqual(policy["loss_pause_require_fresh"], settings.LOSS_PAUSE_REQUIRE_FRESH)

    def test_canonical_data_sources_are_unique_and_valid(self):
        self.assertTrue(DATA_SOURCE_REGISTRY)
        names = [item["name"] for item in DATA_SOURCE_REGISTRY.values()]
        self.assertEqual(len(names), len(set(names)))
        for source in DATA_SOURCE_REGISTRY.values():
            self.assertTrue(source["canonical_key"])
            self.assertTrue(source["path"].startswith(("data/", "runtime/", "analytics/")))

    def test_resolve_data_source_prefers_canonical_source(self):
        resolved = resolve_data_source("truth_layer")
        self.assertIsNotNone(resolved)
        self.assertIn("truth_layer", resolved["canonical_key"])
        self.assertEqual(resolved["path"], "data/truth_layer/trade_history.json")
        self.assertEqual(resolved["category"], "canonical")


if __name__ == "__main__":
    unittest.main()
