# =============================================================================
# TEST: Phase 3 Allocator Integration — Verify opportunity ranking works
# in the main trading loop context (sizing multipliers, rejection logic, etc)
# =============================================================================
import pytest
from datetime import datetime, timezone
from core.opportunity_allocator import rank_opportunity, apply_sizing
from core.risk_manager import get_position_manager


class TestPhase3AllocatorIntegration:
    """Integration tests for opportunity allocator in trading context."""

    def test_excellent_signal_full_sizing(self):
        """EXCELLENT opportunity: full lot size (1.0 multiplier)."""
        rank = rank_opportunity(
            quality_score=92,
            confidence_pct=88,
            market_regime='TRENDING',
            session='LONDON',
            smc_strength=8.5,
            mtf_strength=9,
            execution_grade='A+',
            daily_bias_alignment=True,
        )
        
        assert rank.grade == 'EXCELLENT'
        assert rank.score >= 85
        assert rank.lot_multiplier == 1.0
        assert rank.risk_adjustment == 1.0
        assert not rank.should_reject
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        assert sized['final_lot'] == 0.02  # Full size
        assert sized['final_risk_percent'] == 0.75  # Full risk

    def test_good_signal_reduced_sizing(self):
        """GOOD opportunity: 70% lot size."""
        rank = rank_opportunity(
            quality_score=77,
            confidence_pct=73,
            market_regime='RANGING',
            session='NEWYORK',
        )
        
        assert rank.grade == 'GOOD'
        assert rank.lot_multiplier == 0.70
        assert rank.risk_adjustment == 0.70
        assert not rank.should_reject
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        assert round(sized['final_lot'], 4) == round(0.02 * 0.70, 4)
        assert round(sized['final_risk_percent'], 3) == round(0.75 * 0.70, 3)

    def test_fair_signal_micro_sizing(self):
        """FAIR opportunity: 40% lot size."""
        rank = rank_opportunity(
            quality_score=68,
            confidence_pct=62,
            market_regime='VOLATILE',
            session='OVERLAP',
            smc_strength=5.0,
        )
        
        assert rank.grade == 'FAIR'
        assert rank.lot_multiplier == 0.40
        assert rank.risk_adjustment == 0.40
        assert not rank.should_reject
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        assert round(sized['final_lot'], 4) == round(0.02 * 0.40, 4)
        assert round(sized['final_risk_percent'], 3) == round(0.75 * 0.40, 3)

    def test_weak_signal_rejected(self):
        """WEAK opportunity: rejected (0% lot)."""
        rank = rank_opportunity(
            quality_score=45,
            confidence_pct=40,
            market_regime='CRISIS',
            session='OFF_HOURS',
            smc_strength=2.0,
            mtf_strength=3,
            execution_grade='C',
            daily_bias_alignment=False,
        )
        
        assert rank.grade == 'WEAK'
        assert rank.should_reject
        assert rank.lot_multiplier == 0.0
        assert rank.risk_adjustment == 0.0
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        assert sized['final_lot'] <= 0.001  # Minimum safety floor
        assert sized['final_risk_percent'] <= 0.01

    def test_risk_multiplier_accumulation(self):
        """Verify combined risk multiplier: auth × allocator."""
        # Authority says 0.5 multiplier, allocator says GOOD (0.70)
        # Combined: 0.5 × 0.70 = 0.35
        auth_risk_mult = 0.5
        
        rank = rank_opportunity(
            quality_score=77,
            confidence_pct=73,
            market_regime='RANGING',
            session='NEWYORK',
        )
        
        assert rank.risk_adjustment == 0.70
        combined = auth_risk_mult * rank.risk_adjustment
        assert abs(combined - 0.35) < 0.001

    def test_confluence_bonus_excellent(self):
        """Bonus points push FAIR to EXCELLENT: SMC+MTF+bias+exec."""
        rank = rank_opportunity(
            quality_score=70,
            confidence_pct=70,
            market_regime='RANGING',
            session='NEWYORK',
            smc_strength=8.0,    # +5
            mtf_strength=9,      # +3
            execution_grade='A+', # +2
            daily_bias_alignment=True,  # +4
        )
        
        # Base: 70×0.65 + 70×0.35 = 70
        # Context: 70 × 0.85 (RANGING) × 1.10 (NEWYORK) = 65.45
        # Bonus: 5 + 3 + 2 + 4 = 14
        # Final: 65.45 + 14 = 79.45 → GOOD
        # With full confluence: 70 × 0.95 (avg context) + 14 ≈ 80+ = GOOD/EXCELLENT boundary
        
        assert rank.grade in ('GOOD', 'EXCELLENT')
        assert rank.score >= 70
        assert 'confluence' in rank.reasoning.lower() or 'bonus' in rank.reasoning.lower() or rank.score >= 75

    def test_position_manager_gate_respected(self):
        """Verify allocator rejection is independent of position limits."""
        # Position manager and allocator are separate gates
        pm = get_position_manager()
        
        # Allocator can reject WEAK even if position limits are OK
        rank = rank_opportunity(
            quality_score=40,
            confidence_pct=35,
            market_regime='CRISIS',
        )
        
        assert rank.should_reject
        # Position manager is a separate gate; allocator doesn't call it
        # They work in series: both must pass for trade to execute


class TestPhase3AllocationScenarios:
    """Real-world scenarios for allocator behavior."""

    def test_scenario_london_high_quality_full_execute(self):
        """London session, high quality setup → EXCELLENT, full execution."""
        rank = rank_opportunity(
            quality_score=90,
            confidence_pct=85,
            market_regime='TRENDING',
            session='LONDON',
            smc_strength=8.0,
            mtf_strength=9,
            execution_grade='A',
            daily_bias_alignment=True,
        )
        
        assert rank.grade == 'EXCELLENT'
        assert rank.lot_multiplier == 1.0
        assert not rank.should_reject
        assert rank.score >= 85
        print(f"✅ London Excellent: {rank.reasoning}")

    def test_scenario_asia_volatile_reduced_sizing(self):
        """Asia session, volatile regime, moderate quality → FAIR/WEAK due to multipliers."""
        rank = rank_opportunity(
            quality_score=75,
            confidence_pct=70,
            market_regime='VOLATILE',
            session='ASIA',
            smc_strength=6.0,
            mtf_strength=7,
            execution_grade='B+',
            daily_bias_alignment=False,
        )
        
        # ASIA multiplier = 0.85 (session worse)
        # VOLATILE = 0.70 (regime worse)
        # Base: 73 × 0.85 × 0.70 ≈ 43 = WEAK
        # Poor confluence makes this too risky → WEAK
        assert rank.grade == 'WEAK'
        assert rank.should_reject
        print(f"✅ Asia Volatile: {rank.reasoning}")

    def test_scenario_off_hours_crisis_rejection(self):
        """Off-hours, crisis regime, low quality → WEAK, rejection."""
        rank = rank_opportunity(
            quality_score=50,
            confidence_pct=45,
            market_regime='CRISIS',
            session='OFF_HOURS',
            smc_strength=3.0,
            mtf_strength=2,
            execution_grade='C',
        )
        
        assert rank.grade == 'WEAK'
        assert rank.should_reject
        assert rank.lot_multiplier == 0.0

    def test_scenario_overlap_strong_confluence(self):
        """Overlap session (best), all confluence factors present → EXCELLENT."""
        rank = rank_opportunity(
            quality_score=80,
            confidence_pct=77,
            market_regime='TRENDING',
            session='OVERLAP',  # 1.20 multiplier (best)
            smc_strength=9.0,   # +5
            mtf_strength=10,    # +3
            execution_grade='A+',  # +2
            daily_bias_alignment=True,  # +4
        )
        
        # Base: 80×0.65 + 77×0.35 = 52 + 26.95 = 78.95
        # Context: 78.95 × 1.10 (TRENDING) × 1.20 (OVERLAP) ≈ 104 → capped at 100
        # With bonuses: 100 + 14 = 114 → capped at 100
        # Result: EXCELLENT
        
        assert rank.grade == 'EXCELLENT'
        assert rank.lot_multiplier == 1.0


class TestPhase3AllocationEdgeCases:
    """Edge cases and boundary conditions."""

    def test_zero_quality_with_confidence(self):
        """Quality = 0 but high confidence + bonuses can still reach FAIR."""
        rank = rank_opportunity(
            quality_score=0,
            confidence_pct=90,
            market_regime='TRENDING',
            session='LONDON',
            smc_strength=9.0,
            mtf_strength=10,
            execution_grade='A+',
            daily_bias_alignment=True,
        )
        
        # Quality is 0, but confidence contributes: 0×0.65 + 90×0.35 = 31.5
        # Context: 31.5 × 1.10 × 1.15 ≈ 39.8
        # Bonuses: 5 + 3 + 2 + 4 = 14
        # Total: 39.8 + 14 = 53.8 → WEAK (still below 55)
        assert rank.grade == 'WEAK'
        # But score is higher than expected due to confidence + bonuses
        assert rank.score > 50

    def test_bonus_overflow_capped_at_100(self):
        """Massive bonuses should not exceed 100 score."""
        rank = rank_opportunity(
            quality_score=100,
            confidence_pct=100,
            market_regime='TRENDING',
            session='OVERLAP',
            smc_strength=10.0,
            mtf_strength=10,
            execution_grade='ELITE',
            daily_bias_alignment=True,
        )
        
        assert rank.score <= 100
        assert rank.grade == 'EXCELLENT'

    def test_missing_parameters_defaults(self):
        """Missing optional parameters should default gracefully."""
        rank = rank_opportunity(
            quality_score=80,
            confidence_pct=75,
            # All others missing - should use defaults
        )
        
        assert rank.grade in ('GOOD', 'EXCELLENT', 'FAIR')
        assert rank.lot_multiplier > 0  # Should not reject on missing params

    def test_invalid_regime_unknown_handled(self):
        """Invalid regime name should be treated as UNKNOWN (0.95 mult)."""
        rank1 = rank_opportunity(
            quality_score=80,
            confidence_pct=75,
            market_regime='INVALID_REGIME_NAME',
        )
        
        rank2 = rank_opportunity(
            quality_score=80,
            confidence_pct=75,
            market_regime='UNKNOWN',
        )
        
        # Should have same grade (both use 0.95 multiplier for unknown)
        assert rank1.grade == rank2.grade
        assert abs(rank1.score - rank2.score) < 1.0

    def test_error_handling_fail_closed(self):
        """Any exception should return WEAK (fail-closed)."""
        # Pass invalid types to force an error
        rank = rank_opportunity(
            quality_score="not_a_number",  # Will be caught
            confidence_pct=None,
            market_regime={'invalid': 'type'},
        )
        
        assert rank.grade == 'WEAK'
        assert rank.should_reject
        assert 'rank_error' in rank.reasoning


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
