from datetime import datetime, timezone

from core.test_mode_manager import save_state
from core.unified_decision import DecisionContext, unified_decide


def test_counter_trend_is_capped_to_micro_half_risk():
    save_state({"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "used_micro": 0, "used_normal": 0, "used_total": 0})
    ctx = DecisionContext(
        strategy="SMC",
        signal="SELL",
        quality_score=80,
        confidence_pct=70,
        brain_score=75,
        execution_score=72,
        context_score=70,
        daily_bias="BUY",
        mtf_strength=2,
        smc_strength=6.5,
        smc_entry_confirmed=True,
        candle_trigger_confirmed=True,
        liquidity_alignment=70,
        sweep_probability=100,
        session="LONDON",
        market_regime="RANGING",
        spread_ratio=0.05,
        atr_sufficient=True,
        rr_ratio=2.0,
        ml_score=60,
        ml_rl_action="PASS",
    )
    result = unified_decide(ctx)
    assert result.size_mode == "MICRO"
    assert result.risk_multiplier <= 0.5
    assert result.debug["counter_trend_active"] is True
