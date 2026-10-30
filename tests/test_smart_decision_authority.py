from core.unified_decision import DecisionContext, unified_decide


def test_smart_authority_classifies_reduced_entry_for_conflicting_signals():
    ctx = DecisionContext(
        strategy="SMC",
        signal="BUY",
        quality_score=68,
        confidence_pct=63,
        brain_score=70,
        execution_score=72,
        context_score=70,
        daily_bias="NONE",
        mtf_strength=2,
        smc_strength=7.5,
        smc_entry_confirmed=True,
        candle_trigger_confirmed=True,
        liquidity_alignment=78,
        sweep_probability=74,
        session="LONDON",
        market_regime="TRENDING",
        spread_ratio=0.04,
        atr_sufficient=True,
        rr_ratio=1.8,
        ml_score=28,
        ml_rl_action="PASS",
    )
    ctx.execution_grade = "A"
    ctx.volatility = "NORMAL"
    ctx.structure_quality = 68
    ctx.trend_strength = 0.82
    ctx.market_structure = "BOS"
    ctx.liquidity_strength = 76.0
    ctx.model_confidence = 58.0
    ctx.strategy_performance = 62.0

    result = unified_decide(ctx)

    assert result.debug["smart_entry_classification"] in {"REDUCED_ENTRY", "MICRO_ENTRY"}
    assert "SMART_DECISION" in result.debug["smart_explanation"]
    assert result.size_mode in {"REDUCED", "MICRO"}


def test_smart_authority_blocks_weak_signals_from_reduced_or_micro_path():
    ctx = DecisionContext(
        strategy="SMC",
        signal="BUY",
        quality_score=58,
        confidence_pct=60,
        brain_score=58,
        execution_score=55,
        context_score=56,
        daily_bias="NONE",
        mtf_strength=0,
        smc_strength=2.2,
        smc_entry_confirmed=False,
        candle_trigger_confirmed=False,
        liquidity_alignment=52,
        sweep_probability=40,
        session="LONDON",
        market_regime="RANGING",
        spread_ratio=0.03,
        atr_sufficient=True,
        rr_ratio=1.1,
        ml_score=20,
        ml_rl_action="PASS",
    )
    ctx.execution_grade = "C"
    ctx.volatility = "NORMAL"
    ctx.structure_quality = 45
    ctx.trend_strength = 0.35
    ctx.market_structure = "UNKNOWN"
    ctx.liquidity_strength = 50.0
    ctx.model_confidence = 50.0
    ctx.strategy_performance = 48.0

    result = unified_decide(ctx)

    assert result.decision == "HARD_BLOCK"
    assert result.size_mode == "NONE"
