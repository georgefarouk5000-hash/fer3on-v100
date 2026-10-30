import unittest
from unittest.mock import patch

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.multi_tp import get_tp_ladder, compute_tp_prices
from core.settings import MULTI_TP_ENABLED, MULTI_TP_PROFILE


class TestTplLadder(unittest.TestCase):
    def test_get_tp_ladder_profiles(self):
        self.assertTrue(MULTI_TP_ENABLED)
        ladder = get_tp_ladder('SMC')
        self.assertEqual(ladder['mode'], 'LADDER')
        self.assertEqual(len(ladder['targets']), 3)
        self.assertEqual(ladder['targets'][0]['label'], 'TP1')
        self.assertEqual(ladder['targets'][0]['pct'], float(MULTI_TP_PROFILE['SMC']['tp1_pct']))

    def test_compute_tp_prices_buy_sell(self):
        result = compute_tp_prices(entry_price=2000.0, sl_distance=10.0, direction='BUY', strategy='SMC')
        self.assertTrue(result['enabled'])
        self.assertEqual(result['levels'][0]['price'], 2012.0)
        self.assertEqual(result['levels'][1]['price'], 2025.0)
        self.assertEqual(result['levels'][2]['price'], 2040.0)

        result = compute_tp_prices(entry_price=2000.0, sl_distance=10.0, direction='SELL', strategy='SMC')
        self.assertEqual(result['levels'][0]['price'], 1988.0)
        self.assertEqual(result['levels'][1]['price'], 1975.0)
        self.assertEqual(result['levels'][2]['price'], 1960.0)

    def test_compute_tp_prices_bounds_ladder_at_final_target(self):
        result = compute_tp_prices(
            entry_price=2000.0,
            sl_distance=10.0,
            direction='BUY',
            strategy='SMC',
            max_tp_distance=15.0,
        )
        self.assertEqual(
            [(level['label'], level['price'], level['close_pct']) for level in result['levels']],
            [('TP1', 2012.0, 0.5), ('TP_FINAL', 2015.0, 0.5)],
        )

        sell_result = compute_tp_prices(
            entry_price=2000.0,
            sl_distance=10.0,
            direction='SELL',
            strategy='SMC',
            max_tp_distance=25.0,
        )
        self.assertEqual(sell_result['levels'][-1]['price'], 1975.0)
        self.assertEqual(sell_result['levels'][-1]['close_pct'], 0.5)

    def test_compute_tp_prices_fails_closed_for_invalid_final_target(self):
        result = compute_tp_prices(
            entry_price=2000.0,
            sl_distance=10.0,
            direction='BUY',
            strategy='SMC',
            max_tp_distance=float('nan'),
        )
        self.assertFalse(result['enabled'])
        self.assertEqual(result['reason'], 'INVALID_FINAL_TP_DISTANCE')

    def test_compute_tp_prices_disabled(self):
        if not MULTI_TP_ENABLED:
            self.skipTest('MULTI_TP must be enabled for this test')
        result = compute_tp_prices(entry_price=0.0, sl_distance=10.0, direction='BUY', strategy='SMC')
        self.assertFalse(result['enabled'])
        self.assertIn(result['reason'], ('INVALID_INPUT', 'SMC_LADDER'))

    def test_get_tp_ladder_strategy_disabled(self):
        with patch.dict('execution.multi_tp.MULTI_TP_STRATEGY_ENABLED', {'SMC': False}, clear=False):
            ladder = get_tp_ladder('SMC')
            self.assertFalse(ladder['enabled'])
            self.assertEqual(ladder['mode'], 'DISABLED')
            self.assertEqual(ladder['reason'], 'SMC_MULTI_TP_DISABLED')
            self.assertEqual(ladder['targets'], [])

    def test_compute_tp_prices_strategy_disabled(self):
        with patch.dict('execution.multi_tp.MULTI_TP_STRATEGY_ENABLED', {'SMC': False}, clear=False):
            result = compute_tp_prices(entry_price=2000.0, sl_distance=10.0, direction='BUY', strategy='SMC')
            self.assertFalse(result['enabled'])
            self.assertEqual(result['reason'], 'SMC_MULTI_TP_DISABLED')
            self.assertEqual(result['levels'], [])


if __name__ == '__main__':
    unittest.main()
