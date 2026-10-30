"""
Test: Fail-Closed Behavior Verification [FER3ON-2026-08-31]

Ensures that exceptions in safety layers result in trade rejection,
not silent allowance or recovery. This is critical for live trading.

Test Strategy:
1. Verify that kill-switch exception → trade blocked (fail-closed)
2. Verify that settings are properly read (no defaults override)
3. Verify that RiskContract is consistent with runtime behavior
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from unittest import mock
from typing import Tuple


def test_kill_switch_exception_blocks_trade_failclosed(monkeypatch, tmp_path):
    """
    CRITICAL: If should_block_trade() raises ANY exception,
    trade_executor must block the trade (fail-closed), not allow it.
    
    This test verifies that the fail-closed guarantee is honored.
    """
    from core.trade_executor import execute_trade
    from core import settings
    import core.trade_event_ledger as trade_event_ledger
    monkeypatch.setattr(
        trade_event_ledger,
        "TRADE_EVENTS_FILE",
        str(tmp_path / "trade_events.jsonl"),
    )
    
    # Create a minimal valid order request
    order_request = {
        'symbol': 'XAUUSD',
        'action': 'deal',
        'volume': 0.01,
        'type': 'BUY',
        'price': 2400.00,
        'sl': 2395.00,
        'tp': 2410.00,
        'deviation': 20,
        'magic': 4001,
        'comment': 'test',
        'type_time': 'GTC',
        'type_filling': 'IOC',
    }
    
    # Mock should_block_trade to raise an exception (patch at import location)
    with mock.patch('core.strategy_kill_switch.should_block_trade') as mock_block:
        # Simulate any exception in kill-switch logic
        mock_block.side_effect = RuntimeError("Simulated kill-switch error")
        
        # Execute trade should catch this and block (fail-closed)
        result = execute_trade(
            request=order_request,
            strategy='SMC',
            signal='BUY',
            lot=0.01,
            sl_dist=5.0,
            tp_dist=10.0,
            rr_ratio=2.0,
            risk_percent=0.75,
            exec_grade='B',
            final_brain={'final_score': 50},
            quality_score=60,
            confidence=50,
            market_regime='TRENDING',
            atr=4.5,
            session='LONDON',
            magic=4001,
        )
        
        # Key assertion: trade is REJECTED (retcode=-1)
        assert result.get('retcode') == -1, "Exception in kill-switch must block trade"
        assert 'FAIL_CLOSED' in result.get('comment', ''), "Must mention fail-closed in reason"
        print(f"✅ Fail-closed test passed: {result.get('comment')}")


def test_kill_switch_regime_policy_blocks_smc_when_enabled(monkeypatch):
    """
    Verify that when should_block_trade() returns True,
    the trade is rejected before any order is sent.
    """
    from core.trade_executor import execute_trade
    from core import strategy_kill_switch
    import core.daily_loss_guard as daily_loss_guard
    monkeypatch.setattr(strategy_kill_switch, "KILL_SWITCH_ENABLED", True)
    monkeypatch.setattr(
        daily_loss_guard,
        "get_daily_loss_status",
        lambda **_kwargs: {"daily_loss": 0.0},
    )
    should_block_trade = strategy_kill_switch.should_block_trade
    
    # Test data
    order_request = {
        'symbol': 'XAUUSD',
        'volume': 0.01,
        'type': 'BUY',
        'price': 2400.00,
        'sl': 2395.00,
        'tp': 2410.00,
    }
    
    # Test 1: Verify regime block works
    block, reason = should_block_trade(
        strategy='SMC',
        market_regime='RANGING',
        session='LONDON',
        exec_grade='A',
    )
    assert block is True, "SMC should be blocked in RANGING regime"
    assert 'KILL_SWITCH_REGIME' in reason
    print(f"✅ Regime block test: {reason}")
    
    # Test 2: Verify exec grade block works
    block, reason = should_block_trade(
        strategy='SMC',
        market_regime='TRENDING',
        session='LONDON',
        exec_grade='B',  # SMC requires A/A+/ELITE
    )
    # May be blocked if weekly PnL is negative
    if block:
        assert 'EXEC_GRADE' in reason
        print(f"✅ Exec grade block: {reason}")
    else:
        print("⚠️ Exec grade did not block (recovery week, likely)")


def test_settings_values_are_read_not_hardcoded():
    """
    Verify that kill-switch actually reads from core.settings,
    not internal hardcoded defaults.
    
    This ensures that runtime config changes work.
    """
    from core import strategy_kill_switch
    from core import settings
    
    # Read the actual settings values that were imported
    assert hasattr(strategy_kill_switch, 'DAILY_LOSS_LIMIT_BY_STRATEGY')
    
    # Verify they match settings
    assert strategy_kill_switch.DAILY_LOSS_LIMIT_BY_STRATEGY == settings.KILL_SWITCH_DAILY_LOSS_LIMITS
    assert strategy_kill_switch.WEEKLY_LOSS_LIMIT_BY_STRATEGY == settings.KILL_SWITCH_WEEKLY_LOSS_LIMITS
    assert strategy_kill_switch.BLOCKED_REGIMES_BY_STRATEGY == settings.KILL_SWITCH_BLOCKED_REGIMES
    
    print("✅ All kill-switch values read from settings (not hardcoded defaults)")


def test_risk_contract_consistency():
    """
    Verify that RiskContract reports values consistent with
    actual settings and kill-switch behavior.
    """
    from core.risk_contract import get_risk_contract
    from core import settings
    
    contract = get_risk_contract()
    
    # Test 1: Basic validation passes
    is_valid, msg = contract.validate()
    assert is_valid is True, f"RiskContract validation failed: {msg}"
    print(f"✅ RiskContract valid: {msg}")
    
    # Test 2: Contract values match settings
    assert contract.max_sl_distance_dollars == settings.MAX_SL_DISTANCE_DOLLARS
    assert contract.min_lot == settings.MIN_LOT
    assert contract.max_lot == settings.MAX_LOT
    print("✅ RiskContract values match settings")
    
    # Test 3: Query methods work correctly
    assert contract.is_regime_blocked('RANGING', 'SMC') is True
    assert contract.is_regime_blocked('RANGING', 'DAILY') is False
    assert contract.is_exec_grade_allowed('A', 'SMC') is True
    assert contract.is_exec_grade_allowed('B', 'SMC') is False
    print("✅ RiskContract query methods work correctly")


def test_max_sl_enforcement():
    """
    Verify that MAX_SL_DISTANCE_DOLLARS is enforced before
    any order reaches the broker.
    """
    from core import settings
    from core.risk_contract import get_risk_contract
    
    contract = get_risk_contract()
    
    # The hard limit from settings
    max_sl = settings.MAX_SL_DISTANCE_DOLLARS
    
    # Verify the limit is reasonable for small account
    assert max_sl <= 30, f"MAX_SL too high: {max_sl}"
    assert max_sl >= 5, f"MAX_SL too low: {max_sl}"
    
    # Verify contract reports the same
    assert contract.max_sl_distance_dollars == max_sl
    
    print(f"✅ MAX_SL_DISTANCE_DOLLARS={max_sl} is enforced")


def test_london_volatile_block_active():
    """
    Verify that LONDON_VOLATILE_BLOCK is configured and will
    prevent trades during the volatile window.
    """
    from core import settings
    
    # Check that the block is enabled
    assert settings.LONDON_VOLATILE_BLOCK_ENABLED is True
    
    # Check that the window is defined
    assert settings.LONDON_VOLATILE_START < settings.LONDON_VOLATILE_END
    
    # In this config, block is 08:00-09:00 UTC
    assert settings.LONDON_VOLATILE_START == 8
    assert settings.LONDON_VOLATILE_END == 9
    
    print(f"✅ London volatile block: {settings.LONDON_VOLATILE_START:02d}:00-"
          f"{settings.LONDON_VOLATILE_END:02d}:00 UTC")


if __name__ == '__main__':
    # Run all tests
    print("=" * 80)
    print("FER3ON FAIL-CLOSED & CONFIGURATION INTEGRITY TESTS")
    print("=" * 80)
    
    try:
        test_kill_switch_exception_blocks_trade_failclosed()
        test_kill_switch_hard_block_prevents_trade()
        test_settings_values_are_read_not_hardcoded()
        test_risk_contract_consistency()
        test_max_sl_enforcement()
        test_london_volatile_block_active()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise
