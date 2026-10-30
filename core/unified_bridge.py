# =============================================================================
# FER3ON V3-FIXED — UNIFIED BRIDGE
# مُصحّح: context_score من 4 components
# =============================================================================

from typing import Any, Dict, Optional
from datetime import datetime, timezone
from core.unified_decision import (
    DecisionContext,
    DecisionResult,
    format_decision_log,
)
from core.adaptive_learning import (
    get_recent_wr,
    get_recent_losses,
    best_strategy_for_context,
)


def build_decision_context(
    strategy: str,
    signal: str,
    symbol: str = 'XAUUSD',
    quality_score: float = 0.0,
    confidence_pct: float = 0.0,
    brain_score: float = 0.0,
    execution_score: float = 0.0,
    execution_grade: str = 'UNKNOWN',
    structure_quality: float = 50.0,
    daily_bias: str = 'NONE',
    mtf_strength: int = 0,
    smc_strength: float = 0.0,
    smc_entry_confirmed: bool = False,
    candle_trigger_confirmed: bool = False,
    candle_weight: int = 0,
    candle_bonus: float = 0.0,
    candle_penalty: float = 0.0,
    liquidity_alignment: float = 50.0,
    liquidity_bias: str = 'NEUTRAL',
    structure_bias: str = 'NEUTRAL',
    sweep_probability: float = 0.0,
    session: str = 'UNKNOWN',
    market_regime: str = 'RANGING',
    session_score: float = 50.0,
    crisis_active: bool = False,
    news_pause: bool = False,
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    market_unsafe: bool = False,
    daily_loss_capped: bool = False,
    emergency_stop: bool = False,
    spread_ratio: float = 0.0,
    atr_sufficient: bool = True,
    rr_ratio: float = 0.0,
    ml_score: float = 50.0,
    ml_rl_action: str = 'PASS',
    memory_score: float = 50.0,
    dna_score: float = 50.0,
    # §3.2 Institutional Session Engine (docs/FAIE/PHASE_2_SPECIFICATION.md).
    # Optional on purpose: this factory is the real live-loop call site, so
    # when the caller doesn't pass an explicit hour/minute, "right now" (UTC,
    # matching every other UTC-hour session read in main.py) genuinely is
    # the correct value here — unlike testing/faie_backtest.py's historical
    # replay, which deliberately leaves DecisionContext.hour as None instead
    # of guessing "now" for a context that isn't actually happening now.
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> DecisionContext:
    # FIXED: context_score من 4 components
    regime_pts = {
        'TRENDING': 80, 'RANGING': 60, 'VOLATILE': 45,
        'CRISIS': 25, 'UNKNOWN': 50,
    }.get(str(market_regime or 'UNKNOWN').upper(), 50)

    context_score = (
        float(session_score or 50) * 0.30
        + regime_pts * 0.25
        + float(memory_score or 50) * 0.25
        + float(dna_score or 50) * 0.20
    )

    recent_wr = get_recent_wr(window=30)
    recent_losses = get_recent_losses(window=5)

    if hour is None:
        _now = datetime.now(timezone.utc)
        eff_hour, eff_minute = _now.hour, _now.minute
    else:
        eff_hour, eff_minute = hour, (minute if minute is not None else 0)

    return DecisionContext(
        strategy=str(strategy or 'UNKNOWN').upper(),
        signal=str(signal or 'NONE').upper(),
        symbol=symbol,
        quality_score=float(quality_score or 0),
        confidence_pct=float(confidence_pct or 0),
        brain_score=float(brain_score or 0),
        execution_score=float(execution_score or 50),
        execution_grade=str(execution_grade or 'UNKNOWN').upper(),
        structure_quality=float(structure_quality or 50),
        context_score=float(context_score),
        daily_bias=str(daily_bias or 'NONE').upper(),
        mtf_strength=int(mtf_strength or 0),
        smc_strength=float(smc_strength or 0),
        smc_entry_confirmed=bool(smc_entry_confirmed),
        candle_trigger_confirmed=bool(candle_trigger_confirmed),
        candle_weight=int(candle_weight or 0),
        candle_bonus=float(candle_bonus or 0.0),
        candle_penalty=float(candle_penalty or 0.0),
        liquidity_alignment=float(liquidity_alignment or 50),
        sweep_probability=float(sweep_probability or 0),
        session=str(session or 'UNKNOWN').upper(),
        market_regime=str(market_regime or 'RANGING').upper(),
        crisis_active=bool(crisis_active),
        news_pause=bool(news_pause),
        risk_limits_hit=bool(risk_limits_hit),
        cooldown_active=bool(cooldown_active),
        market_unsafe=bool(market_unsafe),
        daily_loss_capped=bool(daily_loss_capped),
        emergency_stop=bool(emergency_stop),
        spread_ratio=float(spread_ratio or 0),
        atr_sufficient=bool(atr_sufficient),
        rr_ratio=float(rr_ratio or 0),
        ml_score=float(ml_score or 50),
        ml_rl_action=str(ml_rl_action or 'PASS').upper(),
        recent_wr=recent_wr,
        recent_losses=recent_losses,
        memory_score=float(memory_score or 50),
        dna_score=float(dna_score or 50),
        hour=int(eff_hour),
        minute=int(eff_minute),
    )


def decide_and_log(ctx: DecisionContext) -> DecisionResult:
    # Import locally to keep the authority facade's bridge dependency acyclic.
    from core.fer3on_decision_authority import decide_trade

    result = decide_trade(ctx)
    print(format_decision_log(result))
    return result


def decision_to_legacy_format(result: DecisionResult) -> Dict[str, Any]:
    return {
        'approved': result.decision != 'HARD_BLOCK',
        'verdict': {
            'PASS_FULL':    'EXECUTE_FULL',
            'PASS_REDUCED': 'EXECUTE_REDUCED',
            'PASS_MICRO':   'EXECUTE_MICRO',
            'HARD_BLOCK':   'REJECT',
        }.get(result.decision, 'REJECT'),
        'mode': result.size_mode,
        'score': result.composite_score,
        'risk_multiplier': result.risk_multiplier,
        'reason': ' | '.join(result.reasons) or 'OK',
        'hard_block_reason': result.hard_block_reason,
        'penalties': result.penalties,
        'bonuses': result.bonuses,
        'debug': result.debug,
    }