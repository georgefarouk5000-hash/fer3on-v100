"""اختبارات StrategyAgentFactory: تتحقق أن كل وكيل يقرأ فعليًا مصدر بياناته
الخاص من context الغني (D1 لـ Daily، M1 لـ Scalp، ملف السيولة لـ SMC، سجل
حقيقي لـ Recovery...) بدل تكرار نفس market_bias، وأن اختلاف المدخلات ينتج
قرارات مختلفة فعليًا."""

from __future__ import annotations

from fer3on_masr.strategy_ai.agents import StrategyAgentFactory


def _base_context(**overrides):
    context = {
        "market_bias": "BUY",
        "base_confidence": 60.0,
        "risk_cap": 0.42,
        "lot_cap": 0.18,
        "timeframes": {},
        "liquidity": {},
        "candles": [],
        "structure_bias": "BUY",
        "structure_confidence": 60.0,
        "news_bias": "NEUTRAL",
        "session": "LONDON",
        "market_regime": "TRENDING",
        "history_stats": {"sample_size": 0, "win_rate": None, "current_losing_streak": 0},
    }
    context.update(overrides)
    return context


def _agents_by_name():
    return {a.name: a for a in StrategyAgentFactory.build_default_agents()}


def test_daily_agent_follows_d1_not_generic_bias():
    agents = _agents_by_name()
    context = _base_context(
        market_bias="SELL",  # التحيّز العام مخالف عمدًا لـ D1
        timeframes={
            "D1": {"timeframe": "D1", "trend": "BUY", "confidence": 80.0, "atr": 5.0,
                   "momentum": 1.0, "support": 1.0, "resistance": 2.0, "liquidity": "BUY_SIDE", "details": {}},
            "W1": {"timeframe": "W1", "trend": "BUY", "confidence": 75.0, "atr": 6.0,
                   "momentum": 1.0, "support": 1.0, "resistance": 2.0, "liquidity": "BUY_SIDE", "details": {}},
        },
    )
    decision = agents["Daily AI"].evaluate(context, weight=1.0)
    assert decision.action == "BUY"  # يتبع D1 الحقيقي، وليس market_bias العام (SELL)
    assert any("D1 trend=BUY" in r for r in decision.rationale)


def test_scalp_agent_follows_m1_independently_of_daily():
    agents = _agents_by_name()
    context = _base_context(
        timeframes={
            "D1": {"timeframe": "D1", "trend": "BUY", "confidence": 80.0, "atr": 5.0,
                   "momentum": 1.0, "support": 1.0, "resistance": 2.0, "liquidity": "BUY_SIDE", "details": {}},
            "M1": {"timeframe": "M1", "trend": "SELL", "confidence": 65.0, "atr": 1.0,
                   "momentum": -1.0, "support": 1.0, "resistance": 2.0, "liquidity": "SELL_SIDE", "details": {}},
        },
    )
    daily_decision = agents["Daily AI"].evaluate(context, weight=1.0)
    scalp_decision = agents["Scalp AI"].evaluate(context, weight=1.0)
    # نفس context، لكن Daily يقرأ D1 (BUY) وScalp يقرأ M1 (SELL) -> قرارات مختلفة فعليًا
    assert daily_decision.action == "BUY"
    assert scalp_decision.action == "SELL"
    assert daily_decision.action != scalp_decision.action


def test_smc_agent_uses_liquidity_profile_not_plain_trend():
    agents = _agents_by_name()
    context = _base_context(
        structure_bias="SELL",
        structure_confidence=70.0,
        liquidity={
            "buy_side": [2350.0], "sell_side": [2330.0],
            "traps": ["False Breakout Trap"], "sweep_zones": [2330.0, 2350.0],
            "best_target": 2330.0, "details": {},
        },
    )
    decision = agents["SMC AI"].evaluate(context, weight=1.0)
    assert decision.action == "SELL"
    assert any("liquidity" in r.lower() for r in decision.rationale)


def test_recovery_agent_reduces_size_after_losing_streak_instead_of_martingale():
    agents = _agents_by_name()
    calm_context = _base_context(history_stats={"sample_size": 50, "win_rate": 55.0, "current_losing_streak": 0})
    stressed_context = _base_context(history_stats={"sample_size": 50, "win_rate": 40.0, "current_losing_streak": 4})

    calm_decision = agents["Recovery AI"].evaluate(calm_context, weight=1.0)
    stressed_decision = agents["Recovery AI"].evaluate(stressed_context, weight=1.0)

    assert stressed_decision.action == "HOLD"
    # الحجم يجب أن يُقلَّص بعد سلسلة خسائر حقيقية، وليس أن يُضاعَف (anti-martingale)
    assert stressed_decision.suggested_lot < calm_decision.suggested_lot
    assert stressed_decision.risk_pct < calm_decision.risk_pct


def test_recovery_agent_with_no_history_does_not_fabricate_a_streak():
    agents = _agents_by_name()
    context = _base_context(history_stats={"sample_size": 0, "win_rate": None, "current_losing_streak": 0})
    decision = agents["Recovery AI"].evaluate(context, weight=1.0)
    assert decision.action != "HOLD"
    assert any("no real trade history" in r for r in decision.rationale)


def test_news_agent_is_defensive_only_when_news_bias_is_active():
    agents = _agents_by_name()
    neutral_context = _base_context(news_bias="NEUTRAL")
    active_context = _base_context(news_bias="SELL")

    neutral_decision = agents["News AI"].evaluate(neutral_context, weight=1.0)
    active_decision = agents["News AI"].evaluate(active_context, weight=1.0)

    assert neutral_decision.action == "BUY"  # يتبع market_bias بثقة مخفّضة فقط
    assert active_decision.action == "SELL"
    assert active_decision.confidence > neutral_decision.confidence


def test_all_seven_agents_have_distinct_kinds():
    agents = StrategyAgentFactory.build_default_agents()
    kinds = {a.kind for a in agents}
    assert len(kinds) == 7  # سبعة وكلاء، سبعة أنواع منطق مختلفة فعليًا


def test_agents_do_not_all_produce_identical_decisions_given_rich_context():
    # الاختبار المحوري لنقطة ضعف "نفس market_bias": مع context غني يحمل
    # اختلافات حقيقية بين الأطر الزمنية، يجب ألا تتطابق كل قرارات الوكلاء.
    agents = _agents_by_name()
    context = _base_context(
        market_bias="BUY",
        structure_bias="SELL",
        news_bias="SELL",
        history_stats={"sample_size": 30, "win_rate": 35.0, "current_losing_streak": 3},
        timeframes={
            "D1": {"timeframe": "D1", "trend": "BUY", "confidence": 90.0, "atr": 5.0,
                   "momentum": 1.0, "support": 1.0, "resistance": 2.0, "liquidity": "BUY_SIDE", "details": {}},
            "M1": {"timeframe": "M1", "trend": "SELL", "confidence": 55.0, "atr": 1.0,
                   "momentum": -1.0, "support": 1.0, "resistance": 2.0, "liquidity": "SELL_SIDE", "details": {}},
        },
        liquidity={"buy_side": [10.0], "sell_side": [5.0], "traps": [], "sweep_zones": [5.0, 10.0], "best_target": 5.0, "details": {}},
    )
    decisions = {name: agent.evaluate(context, weight=1.0) for name, agent in agents.items()}
    actions = {d.action for d in decisions.values()}
    assert len(actions) > 1  # ليست كلها نفس الفعل رغم أنها تشترك في نفس market_bias العام
