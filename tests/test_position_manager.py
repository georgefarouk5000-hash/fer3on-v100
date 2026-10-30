import pytest
from unittest.mock import patch

from core.risk_manager import PositionManager, get_position_manager
from core.position_manager import manage_open_positions


def test_position_manager_type_and_gate():
    manager = PositionManager()
    result = manager.evaluate(strategy='SMC', current_positions=20, total_positions=4)
    assert result['allowed'] is False
    assert 'POSITION_LIMIT' in result['reason']

    gate = get_position_manager().can_open(strategy='MICRO', current_positions=0, total_positions=1)
    assert gate[0] is True
    assert gate[1]['strategy'] == 'MICRO'


def test_management_facade_coordinates_trailing_and_tp_monitor():
    with patch('core.trailing_stop.update_position_trailing') as trailing, \
            patch('execution.tp_monitor.process_tp_ladders') as tp_monitor:
        result = manage_open_positions('XAUUSD', 3.0, mt5_available=True)

    assert result['ok'] is True
    assert result['trailing_ran'] is True
    assert result['tp_monitor_ran'] is True
    trailing.assert_called_once_with('XAUUSD', 3.0)
    tp_monitor.assert_called_once_with('XAUUSD')


def test_management_facade_is_noop_without_mt5():
    result = manage_open_positions('XAUUSD', 3.0, mt5_available=False)

    assert result == {
        'ok': True,
        'trailing_ran': False,
        'tp_monitor_ran': False,
        'errors': [],
    }
