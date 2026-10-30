import unittest
from unittest.mock import MagicMock, patch

import execution.multi_tp as multi_tp
from execution.tp_monitor import process_tp_ladders, next_pending_target, target_hit


class TestTpMonitor(unittest.TestCase):
    def setUp(self):
        multi_tp._TP_LADDER_REGISTRY.clear()

    def test_next_pending_target_skips_closed_levels(self):
        levels = [
            {'label': 'TP1', 'price': 2010.0, 'close_pct': 0.5},
            {'label': 'TP2', 'price': 2018.0, 'close_pct': 0.3},
        ]
        self.assertEqual(next_pending_target(levels, []), levels[0])
        self.assertEqual(next_pending_target(levels, ['TP1']), levels[1])
        self.assertIsNone(next_pending_target(levels, ['TP1', 'TP2']))

    def test_target_hit_buy_and_sell(self):
        self.assertTrue(target_hit('BUY', 2010.0, 2010.0))
        self.assertTrue(target_hit('BUY', 2015.0, 2010.0))
        self.assertFalse(target_hit('BUY', 2009.0, 2010.0))

        self.assertTrue(target_hit('SELL', 1990.0, 1990.0))
        self.assertTrue(target_hit('SELL', 1985.0, 1990.0))
        self.assertFalse(target_hit('SELL', 1995.0, 1990.0))

    @patch('execution.tp_monitor._round_volume', return_value=0.5)
    def test_process_tp_ladders_partial_close(self, fake_round_volume):
        fake_mt5 = MagicMock()
        fake_mt5.TRADE_ACTION_DEAL = 1
        fake_mt5.ORDER_TYPE_SELL = 1
        fake_mt5.POSITION_TYPE_BUY = 0
        fake_mt5.TRADE_RETCODE_DONE = 10009

        fake_tick = MagicMock(bid=2011.0, ask=2011.5)
        fake_position = MagicMock()
        fake_position.ticket = 123
        fake_position.type = fake_mt5.POSITION_TYPE_BUY
        fake_position.volume = 1.0

        fake_mt5.symbol_info_tick.return_value = fake_tick
        fake_mt5.positions_get.return_value = [fake_position]
        fake_mt5.order_send.return_value = MagicMock(retcode=fake_mt5.TRADE_RETCODE_DONE)

        with patch('execution.tp_monitor.mt5', fake_mt5), patch('execution.tp_monitor.MT5_AVAILABLE', True):
            multi_tp.register_tp_ladder(123, {
                'enabled': True,
                'levels': [
                    {'label': 'TP1', 'price': 2010.0, 'close_pct': 0.5},
                    {'label': 'TP2', 'price': 2018.0, 'close_pct': 0.3},
                ],
                'closed_labels': [],
                'base_volume': 1.0,
            })

            process_tp_ladders('EURUSD')

            fake_mt5.order_send.assert_called_once()
            self.assertEqual(multi_tp.get_registered_ladder(123)['closed_labels'], ['TP1'])

    @patch('execution.tp_monitor._round_volume', return_value=0.5)
    def test_process_tp_ladders_restores_registry_after_restart(self, fake_round_volume):
        fake_mt5 = MagicMock()
        fake_mt5.TRADE_ACTION_DEAL = 1
        fake_mt5.ORDER_TYPE_SELL = 1
        fake_mt5.POSITION_TYPE_BUY = 0
        fake_mt5.TRADE_RETCODE_DONE = 10009

        fake_tick = MagicMock(bid=2013.0, ask=2013.5)
        fake_position = MagicMock()
        fake_position.ticket = 789
        fake_position.type = fake_mt5.POSITION_TYPE_BUY
        fake_position.volume = 1.0
        fake_position.price_open = 2000.0
        fake_position.sl = 1990.0
        fake_position.comment = 'SMC'

        fake_mt5.symbol_info_tick.return_value = fake_tick
        fake_mt5.positions_get.return_value = [fake_position]
        fake_mt5.order_send.return_value = MagicMock(retcode=fake_mt5.TRADE_RETCODE_DONE)

        with patch('execution.tp_monitor.mt5', fake_mt5), patch('execution.tp_monitor.MT5_AVAILABLE', True):
            process_tp_ladders('EURUSD')

            restored = multi_tp.get_registered_ladder(789)
            self.assertIsNotNone(restored)
            self.assertTrue(restored['restored_after_restart'])
            self.assertEqual(restored['closed_labels'], ['TP1'])
            fake_mt5.order_send.assert_called_once()

    @patch('execution.tp_monitor._round_volume', return_value=0.5)
    def test_partial_close_request_carries_position_magic(self, fake_round_volume):
        """Regression test: partial TP-ladder closes were being sent with no
        magic field at all, so MT5 defaulted the resulting deal to magic=0.
        Confirmed in production: 8 real trades (net +$154.36) closed with
        magic=0 and were invisible to every strategy-attribution and sync
        step, since resolve_trade_identity() can't map magic=0 to a
        strategy. Fix: the partial-close request must carry the parent
        position's own magic number."""
        fake_mt5 = MagicMock()
        fake_mt5.TRADE_ACTION_DEAL = 1
        fake_mt5.ORDER_TYPE_SELL = 1
        fake_mt5.POSITION_TYPE_BUY = 0
        fake_mt5.TRADE_RETCODE_DONE = 10009

        fake_tick = MagicMock(bid=2011.0, ask=2011.5)
        fake_position = MagicMock()
        fake_position.ticket = 456
        fake_position.type = fake_mt5.POSITION_TYPE_BUY
        fake_position.volume = 1.0
        fake_position.magic = 4001  # SMC_MAGIC

        fake_mt5.symbol_info_tick.return_value = fake_tick
        fake_mt5.positions_get.return_value = [fake_position]
        fake_mt5.order_send.return_value = MagicMock(retcode=fake_mt5.TRADE_RETCODE_DONE)

        with patch('execution.tp_monitor.mt5', fake_mt5), patch('execution.tp_monitor.MT5_AVAILABLE', True):
            multi_tp.register_tp_ladder(456, {
                'enabled': True,
                'levels': [{'label': 'TP1', 'price': 2010.0, 'close_pct': 0.5}],
                'closed_labels': [],
                'base_volume': 1.0,
            })

            process_tp_ladders('EURUSD')

            sent_request = fake_mt5.order_send.call_args[0][0]
            self.assertIn('magic', sent_request)
            self.assertEqual(sent_request['magic'], 4001)

    @patch('execution.tp_monitor._round_volume', return_value=0.5)
    def test_process_tp_ladders_forgets_ticket_when_all_targets_closed(self, fake_round_volume):
        fake_mt5 = MagicMock()
        fake_mt5.TRADE_ACTION_DEAL = 1
        fake_mt5.ORDER_TYPE_SELL = 1
        fake_mt5.POSITION_TYPE_BUY = 0
        fake_mt5.TRADE_RETCODE_DONE = 10009

        fake_tick = MagicMock(bid=2019.0, ask=2019.5)
        fake_position = MagicMock()
        fake_position.ticket = 321
        fake_position.type = fake_mt5.POSITION_TYPE_BUY
        fake_position.volume = 0.5

        fake_mt5.symbol_info_tick.return_value = fake_tick
        fake_mt5.positions_get.return_value = [fake_position]
        fake_mt5.order_send.return_value = MagicMock(retcode=fake_mt5.TRADE_RETCODE_DONE)

        with patch('execution.tp_monitor.mt5', fake_mt5), patch('execution.tp_monitor.MT5_AVAILABLE', True):
            multi_tp.register_tp_ladder(321, {
                'enabled': True,
                'levels': [
                    {'label': 'TP1', 'price': 2010.0, 'close_pct': 0.5},
                ],
                'closed_labels': [],
                'base_volume': 0.5,
            })

            process_tp_ladders('EURUSD')
            self.assertIsNone(multi_tp.get_registered_ladder(321))


if __name__ == '__main__':
    unittest.main()
