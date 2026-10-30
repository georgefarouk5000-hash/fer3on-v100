import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSMCEntryGate(unittest.TestCase):
    def test_unconfirmed_grade_c_is_blocked(self):
        from core.smc_entry_engine import should_allow_smc_entry

        self.assertFalse(should_allow_smc_entry(False, "C"))

    def test_unconfirmed_none_grade_is_blocked(self):
        from core.smc_entry_engine import should_allow_smc_entry

        self.assertFalse(should_allow_smc_entry(False, "NONE"))

    def test_confirmed_entry_is_allowed(self):
        from core.smc_entry_engine import should_allow_smc_entry

        self.assertTrue(should_allow_smc_entry(True, "B+"))


if __name__ == "__main__":
    unittest.main()
