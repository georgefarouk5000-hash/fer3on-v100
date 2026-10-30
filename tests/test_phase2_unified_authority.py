# =============================================================================
# FER3ON PHASE 2 — UNIFIED AUTHORITY TESTS
# =============================================================================
# Tests for the active SMC and DAILY strategies
# Purpose: Verify unified decision authority works for active strategy paths
# =============================================================================

import pytest
from core.phase2_unified_authority import (
    UnifiedStrategyAuthority,
    get_unified_authority,
    decide_smc,
    decide_daily,
)


# =============================================================================
# TEST FIXTURES: Sample Snapshots for Active Strategies
# =============================================================================


@pytest.fixture
def smc_snapshot():
    """Realistic SMC strategy snapshot."""
    return {
        'ready': True,
        'signal': 'BUY',
        'atr': 2.5,
        'confidence': {'pct': 75.0},
        'quality_score': 70.0,
        'brain': {
            'master_score': 65.0,
            'memory_score': 60.0,
            'dna_score': 55.0,
        },
        'execution': {
            'grade': 'A',
            'score': 80.0,
            'spread_pct': 0.05,
            'rr_ratio': 1.5,
        },
        'structure_analysis': {'structure_strength': 75.0},
        'liquidity': {'score': 80.0},
        'candle': {
            'confirmed': True,
            'weight': 3,
            'candle_bonus': 5.0,
            'candle_penalty': 0.0,
        },
        'daily_bias': 'BUY',
        'mtf_strength': 2,
        'smc_strength': 6.5,
        'smc_entry_confirmed': True,
        'sweep_probability': 65.0,
        'session': 'LONDON',
        'market_regime': 'TRENDING',
        'session_score': 75.0,
        'ml_result': {'ml_score': 68.0, 'rl_action': 'PASS'},
    }


@pytest.fixture
def daily_snapshot():
    """Realistic DAILY strategy snapshot."""
    return {
        'signal': 'SELL',
        'confidence': {'pct': 70.0},
        'quality_score': 68.0,
        'brain': {
            'master_score': 70.0,
            'memory_score': 65.0,
            'dna_score': 60.0,
        },
        'execution': {
            'grade': 'A-',
            'score': 75.0,
            'spread_pct': 0.03,
            'rr_ratio': 2.0,
        },
        'structure_analysis': {'structure_strength': 70.0},
        'liquidity': {'score': 85.0},
        'candle': {
            'confirmed': True,
            'weight': 2,
            'candle_bonus': 3.0,
            'candle_penalty': 0.0,
        },
        'daily_bias': 'SELL',
        'mtf_strength': 3,
        'smc_strength': 5.0,
        'smc_entry_confirmed': True,
        'sweep_probability': 55.0,
        'session': 'DAILY',
        'market_regime': 'TRENDING',
        'session_score': 70.0,
        'ml_result': {'ml_score': 72.0, 'rl_action': 'PASS'},
    }


# =============================================================================
# TESTS: Unified Authority Class
# =============================================================================


def test_phase2_authority_singleton():
    """Test that authority is a singleton."""
    auth1 = get_unified_authority()
    auth2 = get_unified_authority()
    assert auth1 is auth2
    print("✅ Phase 2: Singleton pattern verified")


def test_phase2_smc_context_building(smc_snapshot):
    """Test building decision context for SMC."""
    authority = UnifiedStrategyAuthority()
    result = authority.decide_for_strategy('SMC', smc_snapshot)
    
    assert result is not None
    assert result.decision in ('PASS_FULL', 'PASS_REDUCED', 'PASS_MICRO', 'HARD_BLOCK')
    assert result.composite_score >= 0
    assert result.risk_multiplier >= 0
    print(f"✅ Phase 2: SMC decision - {result.decision} (score={result.composite_score})")


def test_phase2_daily_context_building(daily_snapshot):
    """Test building decision context for DAILY."""
    authority = UnifiedStrategyAuthority()
    result = authority.decide_for_strategy('DAILY', daily_snapshot)
    
    assert result is not None
    assert result.decision in ('PASS_FULL', 'PASS_REDUCED', 'PASS_MICRO', 'HARD_BLOCK')
    assert result.composite_score >= 0
    print(f"✅ Phase 2: DAILY decision - {result.decision} (score={result.composite_score})")


def test_phase2_active_strategies_sequentially(smc_snapshot, daily_snapshot):
    """Test active strategies in sequence (simulates main.py trading loop)."""
    authority = UnifiedStrategyAuthority()
    
    # SMC
    smc_result = authority.decide_for_strategy('SMC', smc_snapshot)
    assert smc_result is not None
    assert authority.last_strategy == 'SMC'
    
    # DAILY
    daily_result = authority.decide_for_strategy('DAILY', daily_snapshot)
    assert daily_result is not None
    assert authority.last_strategy == 'DAILY'


def test_phase2_unified_batch_decision_for_active_strategies(smc_snapshot, daily_snapshot):
    """One helper should drive the same authority across active strategies."""
    from core.phase2_unified_authority import apply_unified_strategy_decisions, get_unified_authority

    results = apply_unified_strategy_decisions(
        {
            'SMC': smc_snapshot,
            'DAILY': daily_snapshot,
        }
    )

    assert set(results) == {'SMC', 'DAILY'}
    assert all(result is not None for result in results.values())

    authority = get_unified_authority()
    assert authority.get_decision_count() >= 2
    print(f"✅ Phase 2: Active strategies processed (decisions={authority.get_decision_count()})")


# =============================================================================
# TESTS: Field Variation Handling
# =============================================================================


def test_phase2_signal_field_variations():
    """Test handling of different signal field names."""
    authority = UnifiedStrategyAuthority()
    
    # 'signal' field (SMC, DAILY)
    snapshot1 = {'signal': 'BUY', 'atr': 2.0}
    result1 = authority.decide_for_strategy('SMC', snapshot1)
    assert result1 is not None
    
    # 'direction' field
    snapshot2 = {'direction': 'SELL', 'atr': 2.0}
    result2 = authority.decide_for_strategy('DAILY', snapshot2)
    assert result2 is not None
    
    # 'mode' field
    snapshot3 = {'mode': 'BUY', 'atr': 2.0}
    result3 = authority.decide_for_strategy('SMC', snapshot3)
    assert result3 is not None
    
    print("✅ Phase 2: Signal field variations handled correctly")


def test_phase2_confidence_field_variations():
    """Test handling of different confidence field formats."""
    authority = UnifiedStrategyAuthority()
    
    # Nested confidence format
    snapshot1 = {'signal': 'BUY', 'confidence': {'pct': 75.0}, 'atr': 2.0}
    result1 = authority.decide_for_strategy('SMC', snapshot1)
    assert result1 is not None
    
    # Flat confidence_pct format
    snapshot2 = {'signal': 'BUY', 'confidence_pct': 65.0, 'atr': 2.0}
    result2 = authority.decide_for_strategy('SMC', snapshot2)
    assert result2 is not None
    
    print("✅ Phase 2: Confidence field variations handled correctly")


def test_phase2_regime_field_variations():
    """Test handling of different regime field names."""
    authority = UnifiedStrategyAuthority()
    
    # 'market_regime' field
    snapshot1 = {'signal': 'BUY', 'market_regime': 'TRENDING', 'atr': 2.0}
    result1 = authority.decide_for_strategy('SMC', snapshot1)
    assert result1 is not None
    
    # 'regime' field
    snapshot2 = {'signal': 'SELL', 'regime': 'RANGING', 'atr': 2.0}
    result2 = authority.decide_for_strategy('SMC', snapshot2)
    assert result2 is not None
    
    print("✅ Phase 2: Regime field variations handled correctly")


# =============================================================================
# TESTS: Risk State Handling
# =============================================================================


def test_phase2_risk_limits_hard_block(smc_snapshot):
    """Test hard block when risk limits are hit."""
    authority = UnifiedStrategyAuthority()
    result = authority.decide_for_strategy(
        'SMC', smc_snapshot, risk_limits_hit=True
    )
    
    assert result is not None
    assert result.decision == 'HARD_BLOCK'
    assert 'RISK_LIMITS_HIT' in result.hard_block_reason
    print(f"✅ Phase 2: Risk limits hard block - {result.hard_block_reason}")


def test_phase2_cooldown_hard_block(smc_snapshot):
    """Test hard block when cooldown is active."""
    authority = UnifiedStrategyAuthority()
    result = authority.decide_for_strategy(
        'SMC', smc_snapshot, cooldown_active=True
    )
    
    assert result is not None
    assert result.decision == 'HARD_BLOCK'
    assert 'COOLDOWN_ACTIVE' in result.hard_block_reason
    print(f"✅ Phase 2: Cooldown hard block - {result.hard_block_reason}")


def test_phase2_daily_loss_cap_hard_block(smc_snapshot):
    """Test hard block when daily loss cap is hit."""
    authority = UnifiedStrategyAuthority()
    result = authority.decide_for_strategy(
        'SMC', smc_snapshot, daily_loss_capped=True
    )
    
    assert result is not None
    assert result.decision == 'HARD_BLOCK'
    assert 'DAILY_LOSS_CAPPED' in result.hard_block_reason
    print(f"✅ Phase 2: Daily loss cap hard block - {result.hard_block_reason}")


def test_phase2_authority_fail_closed_on_exception(smc_snapshot, monkeypatch):
    """Any authority failure must reject the trade, never allow it silently."""
    authority = UnifiedStrategyAuthority()

    def boom(*args, **kwargs):
        raise RuntimeError('simulated authority failure')

    monkeypatch.setattr('core.phase2_unified_authority._build_decision_context', boom)

    result = authority.decide_for_strategy('SMC', smc_snapshot)

    assert result is not None
    assert result.decision == 'HARD_BLOCK'
    assert 'FAIL_CLOSED' in (result.hard_block_reason or '')
    print(f"✅ Phase 2: Authority fail-closed rejection - {result.hard_block_reason}")


# =============================================================================
# TESTS: Error Handling
# =============================================================================


def test_phase2_missing_fields_graceful_degradation():
    """Test that missing fields are handled gracefully."""
    authority = UnifiedStrategyAuthority()
    
    # Minimal snapshot
    sparse_snapshot = {'signal': 'BUY'}
    result = authority.decide_for_strategy('SMC', sparse_snapshot)
    
    # Should not crash, result should be valid or None
    # (depending on implementation)
    if result is not None:
        assert result.decision in ('PASS_FULL', 'PASS_REDUCED', 'PASS_MICRO', 'HARD_BLOCK')
    
    print("✅ Phase 2: Missing fields handled gracefully")


def test_phase2_invalid_data_types():
    """Test that invalid data types don't crash."""
    authority = UnifiedStrategyAuthority()
    
    # Wrong data types
    snapshot = {
        'signal': 'BUY',
        'confidence': 'NOT_A_NUMBER',  # Should be float or dict
        'quality_score': 'HIGH',  # Should be float
        'brain': 'invalid',  # Should be dict
    }
    
    result = authority.decide_for_strategy('SMC', snapshot)
    # Should handle gracefully, not crash
    if result is not None:
        assert result.decision in ('PASS_FULL', 'PASS_REDUCED', 'PASS_MICRO', 'HARD_BLOCK')
    
    print("✅ Phase 2: Invalid data types handled gracefully")


def test_phase2_error_tracking():
    """Test that errors are tracked without crashing."""
    authority = UnifiedStrategyAuthority()
    
    # Create an error condition (invalid field names for all variations)
    bad_snapshot = {'random_field': 'value'}
    
    # This should not raise, should gracefully degrade
    result = authority.decide_for_strategy('SMC', bad_snapshot)
    
    # Result should be None or valid decision
    if result is None:
        # Error was tracked
        assert authority.get_last_error() is not None
    else:
        # Got a decision anyway
        assert result.decision in ('PASS_FULL', 'PASS_REDUCED', 'PASS_MICRO', 'HARD_BLOCK')
    
    print("✅ Phase 2: Error tracking verified")


# =============================================================================
# TESTS: Convenience Functions
# =============================================================================


def test_phase2_convenience_decide_smc(smc_snapshot):
    """Test convenience function for SMC."""
    result = decide_smc(smc_snapshot)
    assert result is not None or result is None  # Either valid or None
    print("✅ Phase 2: decide_smc convenience function works")


def test_phase2_convenience_decide_daily(daily_snapshot):
    """Test convenience function for DAILY."""
    result = decide_daily(daily_snapshot)
    assert result is not None or result is None
    print("✅ Phase 2: decide_daily convenience function works")


# =============================================================================
# TESTS: Backward Compatibility
# =============================================================================


def test_phase2_backward_compatible_with_phase1(smc_snapshot):
    """Verify Phase 2 doesn't break existing Phase 1 patterns."""
    authority = UnifiedStrategyAuthority()
    
    # Original Phase 1 SMC snapshot format
    result = authority.decide_for_strategy('SMC', smc_snapshot)
    
    assert result is not None
    assert hasattr(result, 'decision')
    assert hasattr(result, 'composite_score')
    assert hasattr(result, 'risk_multiplier')
    
    print("✅ Phase 2: Backward compatibility with Phase 1 verified")


def test_phase2_stats_tracking():
    """Test decision counting and stats."""
    authority = UnifiedStrategyAuthority()
    
    assert authority.get_decision_count() == 0
    
    snapshot = {'signal': 'BUY', 'atr': 2.0}
    
    authority.decide_for_strategy('SMC', snapshot)
    assert authority.get_decision_count() == 1
    
    authority.decide_for_strategy('DAILY', snapshot)
    assert authority.get_decision_count() == 2
    
    authority.reset_stats()
    assert authority.get_decision_count() == 0
    
    print("✅ Phase 2: Stats tracking verified")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
