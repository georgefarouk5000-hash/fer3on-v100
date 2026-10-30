from core.unified_decision import DecisionContext, unified_decide


def test_dynamic_threshold_and_penalties_are_context_aware():
    ctx = DecisionContext(
        strategy="SMC",
        signal="BUY",
        quality_score=82,
        confidence_pct=78,
        brain_score=74,
        execution_score=70,
        context_score=70,
        daily_bias="NONE",
        mtf_strength=0,
        smc_strength=2.5,
        smc_entry_confirmed=False,
        candle_trigger_confirmed=True,
        candle_bonus=4.0,
        liquidity_alignment=82,
        sweep_probability=72,
        session="LONDON",
        market_regime="RANGING",
        spread_ratio=0.02,
        atr_sufficient=True,
        rr_ratio=2.2,
        ml_score=50,
        ml_rl_action="PASS",
    )
    ctx.execution_grade = "A"
    ctx.volatility = "NORMAL"
    ctx.structure_quality = 72

    result = unified_decide(ctx)

    assert result.debug["dynamic_threshold"] <= 50
    assert "ML_WEAK" not in result.penalties
    assert "ML_LOW" not in result.penalties
