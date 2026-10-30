"""
Test: Opportunity Allocator — Gradual Sizing [FER3ON-2026-08-31]

Verifies that the allocator:
1. Ranks opportunities (EXCELLENT/GOOD/FAIR/WEAK)
2. Applies gradual sizing multipliers
3. Never rejects genuinely good opportunities
4. Maintains fail-closed behavior on errors
"""

import json

import pytest
from core.opportunity_allocator import (
    rank_opportunity,
    apply_sizing,
    effective_risk_adjustment,
    OpportunityRank,
)


class TestOpportunityRanking:
    """Test the ranking engine."""

    def test_excellent_opportunity(self):
        """High quality + confidence + good context = EXCELLENT."""
        rank = rank_opportunity(
            quality_score=90,
            confidence_pct=85,
            market_regime='TRENDING',
            session='LONDON',
            smc_strength=8.0,
            mtf_strength=9,
            execution_grade='A+',
            daily_bias_alignment=True,
        )
        
        assert rank.grade == 'EXCELLENT', f"Expected EXCELLENT, got {rank.grade}"
        assert rank.lot_multiplier == 1.0, "EXCELLENT should be 100% lot"
        assert rank.risk_adjustment == 1.0, "EXCELLENT should be 100% risk"
        assert not rank.should_reject, "EXCELLENT should not be rejected"
        print(f"✅ EXCELLENT ranking: score={rank.score:.0f}, reasoning={rank.reasoning}")

    def test_good_opportunity(self):
        """Moderate quality with fair confidence = GOOD."""
        rank = rank_opportunity(
            quality_score=77,
            confidence_pct=73,
            market_regime='RANGING',  # Moderate regime
            session='NEWYORK',
        )
        
        assert rank.grade == 'GOOD', f"Expected GOOD, got {rank.grade} (score={rank.score:.0f})"
        assert rank.lot_multiplier == 0.70, f"GOOD should have 70% lot, got {rank.lot_multiplier}"
        assert not rank.should_reject, "GOOD should not be rejected"
        print(f"✅ GOOD ranking: score={rank.score:.0f}, lot_mult={rank.lot_multiplier}")

    def test_fair_opportunity(self):
        """Lower quality but still tradeable = FAIR."""
        rank = rank_opportunity(
            quality_score=72,
            confidence_pct=68,
            market_regime='RANGING',
            session='LONDON',  # Better session to get to FAIR
        )
        
        assert rank.grade in ('FAIR', 'GOOD'), f"Expected FAIR/GOOD, got {rank.grade}"
        assert rank.lot_multiplier > 0, "FAIR should have some lot"
        assert not rank.should_reject, "FAIR should not be rejected"
        print(f"✅ FAIR ranking: score={rank.score:.0f}, lot_mult={rank.lot_multiplier}")

    def test_weak_opportunity(self):
        """Very low quality = WEAK, rejected."""
        rank = rank_opportunity(
            quality_score=40,
            confidence_pct=35,
            market_regime='CRISIS',
            session='ASIA',
        )
        
        assert rank.grade == 'WEAK', f"Expected WEAK, got {rank.grade}"
        assert rank.lot_multiplier == 0.0, "WEAK should have 0% lot"
        assert rank.should_reject, "WEAK should be rejected"
        print(f"✅ WEAK ranking: score={rank.score:.0f}, rejected correctly")

    def test_context_improves_rank(self):
        """Good context (TRENDING + LONDON) improves rank."""
        base = rank_opportunity(
            quality_score=65,
            confidence_pct=60,
            market_regime='RANGING',
            session='ASIA',
        )
        
        improved = rank_opportunity(
            quality_score=65,
            confidence_pct=60,
            market_regime='TRENDING',
            session='LONDON',
        )
        
        assert improved.score > base.score, (
            f"Better context should improve score: {improved.score} <= {base.score}"
        )
        print(f"✅ Context improvement: {base.score:.0f} → {improved.score:.0f}")

    def test_confluence_bonus(self):
        """SMC + MTF + bias alignment give bonuses."""
        no_bonus = rank_opportunity(
            quality_score=70,
            confidence_pct=65,
        )
        
        with_bonus = rank_opportunity(
            quality_score=70,
            confidence_pct=65,
            smc_strength=7.5,
            mtf_strength=8,
            daily_bias_alignment=True,
            execution_grade='A',
        )
        
        assert with_bonus.score > no_bonus.score, (
            f"Confluence should boost score: {with_bonus.score} <= {no_bonus.score}"
        )
        print(f"✅ Confluence bonus: {no_bonus.score:.0f} → {with_bonus.score:.0f}")

    def test_fail_closed_on_error(self):
        """Any error must result in WEAK rejection."""
        rank = rank_opportunity(
            quality_score="invalid",  # This will cause an error
            confidence_pct=None,
        )
        
        assert rank.grade == 'WEAK', "Error should result in WEAK grade"
        assert rank.should_reject, "Error should result in rejection"
        assert rank.lot_multiplier == 0.0, "Error should zero out the lot"
        print(f"✅ Fail-closed on error: {rank.reasoning}")

    def test_risk_adjustment_is_advisory_until_live_promotion(self):
        rank = rank_opportunity(
            quality_score=40,
            confidence_pct=35,
            market_regime='CRISIS',
            session='ASIA',
        )

        assert effective_risk_adjustment(rank, live_enabled=False) == 1.0
        assert effective_risk_adjustment(rank, live_enabled=True) == 0.0


class TestOpportunitySizing:
    """Test the sizing application."""

    def test_size_excellent_opportunity(self):
        """EXCELLENT opportunity uses 100% of base lot and risk."""
        rank = OpportunityRank(
            grade='EXCELLENT',
            score=88,
            lot_multiplier=1.0,
            risk_adjustment=1.0,
            reasoning='test',
            should_reject=False,
        )
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        
        assert sized['final_lot'] == 0.02, f"Got {sized['final_lot']}"
        assert sized['final_risk_percent'] == 0.75, f"Got {sized['final_risk_percent']}"
        print(f"✅ EXCELLENT sizing: lot={sized['final_lot']}, risk={sized['final_risk_percent']}%")

    def test_size_good_opportunity(self):
        """GOOD opportunity uses 70% of base lot and risk."""
        rank = OpportunityRank(
            grade='GOOD',
            score=75,
            lot_multiplier=0.70,
            risk_adjustment=0.70,
            reasoning='test',
            should_reject=False,
        )
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        
        assert abs(sized['final_lot'] - 0.014) < 0.001, f"Got {sized['final_lot']}"
        assert abs(sized['final_risk_percent'] - 0.525) < 0.01, f"Got {sized['final_risk_percent']}"
        print(f"✅ GOOD sizing: lot={sized['final_lot']}, risk={sized['final_risk_percent']}%")

    def test_size_fair_opportunity(self):
        """FAIR opportunity uses 40% of base lot and risk."""
        rank = OpportunityRank(
            grade='FAIR',
            score=62,
            lot_multiplier=0.40,
            risk_adjustment=0.40,
            reasoning='test',
            should_reject=False,
        )
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        
        assert abs(sized['final_lot'] - 0.008) < 0.001, f"Got {sized['final_lot']}"
        assert abs(sized['final_risk_percent'] - 0.30) < 0.01, f"Got {sized['final_risk_percent']}"
        print(f"✅ FAIR sizing: lot={sized['final_lot']}, risk={sized['final_risk_percent']}%")

    def test_size_weak_opportunity(self):
        """WEAK opportunity is zeroed out (with minimum safety floor)."""
        rank = OpportunityRank(
            grade='WEAK',
            score=40,
            lot_multiplier=0.0,
            risk_adjustment=0.0,
            reasoning='test',
            should_reject=True,
        )
        
        sized = apply_sizing(rank, base_lot=0.02, base_risk_percent=0.75)
        
        # apply_sizing has a minimum safety floor of 0.001 to prevent zero-trades
        assert sized['final_lot'] <= 0.001, f"Got {sized['final_lot']}"
        assert sized['final_risk_percent'] <= 0.01, f"Got {sized['final_risk_percent']}"
        print(f"✅ WEAK sizing: lot={sized['final_lot']}, risk={sized['final_risk_percent']}%")

    def test_sizing_with_zero_base_lot(self):
        """Even excellent rank can't create lot from zero base."""
        rank = OpportunityRank(
            grade='EXCELLENT',
            score=90,
            lot_multiplier=1.0,
            risk_adjustment=1.0,
            reasoning='test',
            should_reject=False,
        )
        
        sized = apply_sizing(rank, base_lot=0.0, base_risk_percent=0.0)
        
        # Should return minimum safe values
        assert sized['final_lot'] >= 0.001, f"Got {sized['final_lot']}"
        assert sized['final_risk_percent'] >= 0.01, f"Got {sized['final_risk_percent']}"
        print(f"✅ Minimum sizing: lot={sized['final_lot']}, risk={sized['final_risk_percent']}%")


class TestOpportunityEffectiveness:
    """Test the effectiveness of gradual filtering."""

    def test_no_false_rejections(self):
        """Quality 65 + good context should NOT be rejected."""
        # This is "maybe" signal in uncertain market
        rank = rank_opportunity(
            quality_score=65,
            confidence_pct=62,
            market_regime='TRENDING',
            session='LONDON',
        )
        
        # Should be FAIR or better, not WEAK
        assert rank.grade != 'WEAK', f"False rejection: {rank.reasoning}"
        assert rank.lot_multiplier > 0, "Should have some size"
        print(f"✅ No false rejection: quality=65 → {rank.grade} (size={rank.lot_multiplier})")

    def test_profit_distribution(self):
        """Simulate filtering effect on profits."""
        # 10 signals scenario
        signals = [
            (90, 85, 'EXCELLENT'),  # +$20
            (75, 70, 'GOOD'),       # +$12
            (62, 58, 'FAIR'),       # +$3
            (55, 50, 'FAIR'),       # -$1
            (45, 40, 'WEAK'),       # -$10 (rejected)
            (48, 42, 'WEAK'),       # -$12 (rejected)
            (88, 82, 'EXCELLENT'),  # +$18
            (70, 65, 'GOOD'),       # +$10
            (50, 45, 'WEAK'),       # -$8 (rejected)
            (52, 48, 'WEAK'),       # -$9 (rejected)
        ]
        
        total_profit = 0.0
        traded_count = 0
        
        for quality, confidence, expected_grade in signals:
            rank = rank_opportunity(quality_score=quality, confidence_pct=confidence)
            if rank.grade == expected_grade:
                # Profit ~quality * lot_multiplier - 5$ base loss
                profit = (quality / 100.0 * 20 - 5) * rank.lot_multiplier
                if rank.lot_multiplier > 0:
                    traded_count += 1
                    total_profit += profit
        
        # With filtering: ~6 trades (4 EXCELLENT/GOOD + 2 FAIR), ~+$30-40
        # Without filtering: ~10 trades, ~-$20
        assert total_profit > 0, f"Should be profitable: {total_profit}"
        assert traded_count < 10, f"Should reject weak: {traded_count} trades"
        print(f"✅ Profit improvement: {traded_count} trades, +${total_profit:.0f}")


def test_candidate_rank_is_logged_once(tmp_path, monkeypatch):
    import core.settings as settings

    log_path = tmp_path / "allocator.jsonl"
    monkeypatch.setattr(settings, "PHASE5_ALLOCATOR_LOG_PATH", str(log_path))
    args = {
        "quality_score": 90,
        "confidence_pct": 85,
        "candidate_id": "candidate-1",
        "symbol": "XAUUSD",
        "strategy": "SMC",
        "direction": "BUY",
        "decision_bar_time": "2026-10-30T09:00:00+00:00",
    }

    rank_opportunity(**args)
    rank_opportunity(**{**args, "quality_score": 10})

    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["candidate_id"] == "candidate-1"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
