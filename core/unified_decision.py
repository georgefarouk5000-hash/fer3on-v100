# =============================================================================
# FER3ON V3-FIXED — UNIFIED DECISION ENGINE
# =============================================================================
# مُصحّح:
#   - context_score يستخدم memory_score + dna_score
#   - COMPOSITE thresholds مُفتّحة
# =============================================================================

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.settings import (
    COMPOSITE_FULL_MIN,
    COMPOSITE_REDUCED_MIN,
    COMPOSITE_MICRO_MIN,
    COMPOSITE_WEIGHTS,
    MTF_HARD_FOR,
    BIAS_HARD_FOR,
    BIAS_ELEVATED_PENALTY_FOR,
    MAX_RISK_TOTAL,
    TESTING_MODE,
)
from core.test_mode_manager import can_allocate as test_mode_can_allocate


@dataclass
class DecisionContext:
    strategy: str = 'UNKNOWN'
    signal: str = 'NONE'
    symbol: str = 'XAUUSD'
    quality_score: float = 0.0
    confidence_pct: float = 0.0
    brain_score: float = 0.0
    execution_score: float = 0.0
    context_score: float = 50.0
    execution_grade: str = 'UNKNOWN'
    volatility: str = 'NORMAL'
    structure_quality: float = 50.0
    atr_value: Optional[float] = None
    trend_strength: float = 0.0
    market_structure: str = 'UNKNOWN'
    liquidity_strength: float = 50.0
    model_confidence: float = 50.0
    strategy_performance: float = 50.0

    daily_bias: str = 'NONE'
    mtf_strength: int = 0
    smc_strength: float = 0.0
    smc_entry_confirmed: bool = False
    candle_trigger_confirmed: bool = False
    candle_weight: int = 0
    # V3.5 PHASE-3.3: candle_trigger.py already computes a richer bonus/
    # penalty pair (up to +6 / -8) than the single candle_weight int below —
    # these were computed but discarded before this fix.
    candle_bonus: float = 0.0
    candle_penalty: float = 0.0
    liquidity_alignment: float = 50.0
    sweep_probability: float = 0.0

    session: str = 'UNKNOWN'
    market_regime: str = 'RANGING'
    session_score: float = 50.0
    # §3.2 Institutional Session Engine (docs/FAIE/PHASE_2_SPECIFICATION.md).
    # Optional — None means "no real clock time available for this context"
    # (e.g. a historical replay via testing/faie_backtest.py), which lets
    # brain.faie.analysts.SessionAnalyst tell the difference between a real
    # sub-window read (core.session_intelligence.detect_session_phase) and a
    # degraded, coarser fallback based on `session` alone, instead of ever
    # guessing "now" for a context that isn't actually happening now.
    hour: Optional[int] = None
    minute: int = 0
    crisis_active: bool = False
    news_pause: bool = False

    risk_limits_hit: bool = False
    cooldown_active: bool = False
    market_unsafe: bool = False
    daily_loss_capped: bool = False
    emergency_stop: bool = False

    spread_ratio: float = 0.0
    atr_sufficient: bool = True
    rr_ratio: float = 0.0

    ml_score: float = 50.0
    ml_rl_action: str = 'PASS'

    recent_wr: float = 0.5
    recent_losses: int = 0

    # FIXED: أضفنا memory_score و dna_score
    memory_score: float = 50.0
    dna_score: float = 50.0

    legacy_score_adjustment: float = 0.0

    # V3.6: Trend Confluence + MTF Alignment Layer (core/trend_confluence.py)
    # trend_bonus/penalty: من خط الترند + القناة على الفريم الأساسي (DAILY/SMC فقط)
    # mtf_alignment_mode: ALIGNED | NEUTRAL | CONFLICT — لا يحظر أبدًا (blocked=False دائمًا)
    # mtf_lot_multiplier / mtf_weight_multiplier: تُستهلك في adaptive_lot_engine + هنا
    trend_confluence_bonus: float = 0.0
    trend_confluence_penalty: float = 0.0
    mtf_alignment_mode: str = 'NEUTRAL'
    mtf_alignment_score_delta: float = 0.0
    mtf_lot_multiplier: float = 1.0
    mtf_weight_multiplier: float = 1.0

    # V6: Quant Engine (analytics/quant_engine.py) — تقييم صحة الاستراتيجية من
    # Sharpe/Sortino/Recovery Factor على سجل صفقاتها الفعلي. لا حظر أبدًا —
    # فقط معامل خطر يُضرَب في اللوت (نفس نمط mtf_lot_multiplier). القيمة
    # الافتراضية 1.0 = محايدة (عيّنة غير كافية بعد أو لم يُستدعَ المحرك).
    quant_risk_multiplier: float = 1.0
    quant_health_tier: str = 'UNKNOWN'



@dataclass
class DecisionResult:
    decision: str = 'HARD_BLOCK'
    composite_score: float = 0.0
    risk_multiplier: float = 0.0
    size_mode: str = 'NONE'
    reasons: List[str] = field(default_factory=list)
    penalties: Dict[str, float] = field(default_factory=dict)
    bonuses: Dict[str, float] = field(default_factory=dict)
    hard_block_reason: Optional[str] = None
    debug: Dict[str, Any] = field(default_factory=dict)


CATASTROPHIC_BLOCKS = (
    'EMERGENCY_STOP',
    'DAILY_LOSS_CAPPED',
    'MARKET_UNSAFE',
    'NEWS_PAUSE',
    'CRISIS_FREEZE',
    'RISK_LIMITS_HIT',
    'COOLDOWN_ACTIVE',
    'NO_SIGNAL',
    'SPREAD_CATASTROPHIC',
    'ATR_INSUFFICIENT',
    'STRATEGY_HARD_GATE',
)


def _hard_block_check(ctx: DecisionContext) -> Optional[str]:
    if ctx.emergency_stop:
        return 'EMERGENCY_STOP'
    if ctx.daily_loss_capped:
        return 'DAILY_LOSS_CAPPED'
    if ctx.market_unsafe:
        return 'MARKET_UNSAFE'
    if ctx.news_pause:
        return 'NEWS_PAUSE'
    if ctx.risk_limits_hit:
        return 'RISK_LIMITS_HIT'
    if ctx.cooldown_active:
        return 'COOLDOWN_ACTIVE'
    if ctx.signal in (None, '', 'NONE'):
        return 'NO_SIGNAL'
    if ctx.spread_ratio > 0.50:
        return 'SPREAD_CATASTROPHIC'
    if not ctx.atr_sufficient:
        return 'ATR_INSUFFICIENT'

    strat = (ctx.strategy or '').upper()
    # V3.6: هذا الفرع مُعطَّل تلقائيًا الآن (MTF_HARD_FOR = BIAS_HARD_FOR = () فاضية
    # في core/settings.py) — لا حذف للكود، فقط لا توجد استراتيجية تستوفي الشرط.
    # الحظر الكامل لتعارض Bias/MTF أصبح soft penalty في _apply_soft_modifiers بدلاً
    # من ذلك (BIAS_CONFLICT / BIAS_CONFLICT_ELEVATED / MTF_TREND_CONFLICT).
    if strat in MTF_HARD_FOR and ctx.mtf_strength == 0:
        return 'STRATEGY_HARD_GATE'
    if strat in BIAS_HARD_FOR:
        if ctx.daily_bias and ctx.daily_bias != 'NONE' and ctx.daily_bias != ctx.signal:
            if strat == 'SMC' and _counter_trend_reversal_ok(ctx):
                pass
            else:
                return 'STRATEGY_HARD_GATE'

    return None


def _normalize(x: float, lo: float = 0, hi: float = 100) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        x = 0.0
    return max(lo, min(hi, x))


def _counter_trend_reversal_ok(ctx: DecisionContext) -> bool:
    bias_conflict = bool(ctx.daily_bias and ctx.daily_bias != 'NONE' and ctx.daily_bias != ctx.signal)
    if not bias_conflict:
        return False
    strategy = (ctx.strategy or '').upper()
    if strategy != 'SMC':
        return False
    smc_score_ok = float(ctx.smc_strength or 0) >= 5.0
    liquidity_sweep_ok = float(ctx.sweep_probability or 0) >= 50.0
    rejection_candle_ok = bool(ctx.candle_trigger_confirmed)
    return smc_score_ok and liquidity_sweep_ok and rejection_candle_ok


def _calc_composite(ctx: DecisionContext) -> Dict[str, float]:
    q = _normalize(ctx.quality_score)
    c = _normalize(ctx.confidence_pct)
    b = _normalize(ctx.brain_score)
    e = _normalize(ctx.execution_score)

    # FIXED: context_score يُحسب من 4 components بدل 2
    regime_pts = {
        'TRENDING': 80, 'RANGING': 60, 'VOLATILE': 45,
        'CRISIS': 25, 'UNKNOWN': 50,
    }.get(str(ctx.market_regime or 'UNKNOWN').upper(), 50)

    ctx_s = (
        float(ctx.session_score or 50) * 0.30
        + regime_pts * 0.25
        + float(ctx.memory_score or 50) * 0.25
        + float(ctx.dna_score or 50) * 0.20
    )

    w = COMPOSITE_WEIGHTS
    composite = (
        q * w['quality']
        + c * w['confidence']
        + b * w['brain']
        + e * w['execution']
        + ctx_s * w['context']
    )
    return {
        'quality': q,
        'confidence': c,
        'brain': b,
        'execution': e,
        'context': ctx_s,
        'composite': round(composite, 2),
    }


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_text(value: Any, default: str = 'UNKNOWN') -> str:
    return str(value or default).upper()


def _is_high_execution_context(ctx: DecisionContext) -> bool:
    execution_grade = _coerce_text(getattr(ctx, 'execution_grade', 'UNKNOWN'))
    return (
        execution_grade in {'A', 'A+', 'ELITE'}
        and _coerce_float(getattr(ctx, 'execution_score', 0), 0.0) >= 65.0
        and _coerce_float(getattr(ctx, 'spread_ratio', 0.0), 0.0) <= 0.10
        and not bool(getattr(ctx, 'risk_limits_hit', False))
        and bool(getattr(ctx, 'candle_trigger_confirmed', False))
        and _coerce_float(getattr(ctx, 'liquidity_alignment', 0.0), 0.0) >= 70.0
    )


def _is_low_atr_context(ctx: DecisionContext) -> bool:
    atr_value = getattr(ctx, 'atr_value', None)
    if atr_value is not None:
        return _coerce_float(atr_value, 0.0) <= 1.2
    regime = _coerce_text(getattr(ctx, 'market_regime', 'UNKNOWN'))
    volatility = _coerce_text(getattr(ctx, 'volatility', 'NORMAL'))
    return regime in {'RANGING', 'UNKNOWN'} and volatility in {'LOW', 'NORMAL'}


def _strong_context_for_penalties(ctx: DecisionContext) -> bool:
    return (
        bool(getattr(ctx, 'candle_trigger_confirmed', False))
        and _coerce_float(getattr(ctx, 'liquidity_alignment', 0.0), 0.0) >= 70.0
        and _coerce_float(getattr(ctx, 'structure_quality', 0.0), 0.0) >= 60.0
    )


def _ml_model_status(ctx: DecisionContext) -> str:
    candidates = [
        'xgb_model.pkl',
        'rl_model.pkl',
        'xgb_scaler.pkl',
        os.path.join('ml', 'xgb_model.pkl'),
        os.path.join('ml', 'rl_model.pkl'),
        os.path.join('ml', 'xgb_scaler.pkl'),
    ]
    for item in candidates:
        if os.path.exists(item):
            return 'AVAILABLE'
    return 'UNAVAILABLE'


def _adaptive_quality_floor(ctx: DecisionContext) -> float:
    regime = _coerce_text(getattr(ctx, 'market_regime', 'UNKNOWN'))
    volatility = _coerce_text(getattr(ctx, 'volatility', 'NORMAL'))
    trend_strength = _coerce_float(getattr(ctx, 'trend_strength', 0.0), 0.0)
    atr_value = _coerce_float(getattr(ctx, 'atr_value', 0.0), 0.0)
    quality = _coerce_float(getattr(ctx, 'quality_score', 0.0), 0.0)
    confidence = _coerce_float(getattr(ctx, 'confidence_pct', 0.0), 0.0)
    liquidity = _coerce_float(getattr(ctx, 'liquidity_alignment', 0.0), 0.0)
    structure = _coerce_float(getattr(ctx, 'structure_quality', 0.0), 0.0)
    execution_grade = _coerce_text(getattr(ctx, 'execution_grade', 'UNKNOWN'))
    execution_score = _coerce_float(getattr(ctx, 'execution_score', 0.0), 0.0)

    floor = 55.0
    if regime == 'CRISIS':
        floor = 65.0
    elif regime == 'VOLATILE' or volatility in {'HIGH', 'EXPLOSIVE'} or atr_value >= 2.2:
        floor = 60.0
    elif regime == 'TRENDING' or trend_strength >= 0.65:
        floor = 55.0
    elif regime == 'RANGING':
        floor = 50.0
    elif trend_strength <= 0.35:
        floor = 70.0

    if regime == 'TRENDING' and trend_strength >= 0.75:
        floor = min(floor, 52.0)
    if regime == 'RANGING' and quality >= 70.0 and confidence >= 70.0 and liquidity >= 70.0 and structure >= 65.0:
        floor = max(48.0, floor - 1.0)
    if quality >= 75.0 and execution_grade in {'A', 'A+', 'ELITE'} and execution_score >= 65.0:
        floor -= 1.0
    if execution_grade in {'A', 'A+', 'ELITE'} and execution_score >= 65.0 and liquidity >= 70.0 and structure >= 65.0:
        floor -= 1.0
    if confidence >= 80.0:
        floor -= 1.0
    if liquidity >= 70.0 and getattr(ctx, 'session', 'UNKNOWN') in {'LONDON', 'NEW_YORK'}:
        floor -= 1.0

    return round(max(47.0, min(70.0, floor + 2.0)), 1)


def calculate_dynamic_entry_threshold(ctx: DecisionContext) -> float:
    floor = _adaptive_quality_floor(ctx)
    confidence = _coerce_float(getattr(ctx, 'confidence_pct', 0.0), 0.0)
    ml_score = _coerce_float(getattr(ctx, 'ml_score', 0.0), 0.0)
    if confidence >= 80.0:
        floor -= 1.0
    if ml_score <= 25.0:
        floor += 2.0
    if ml_score >= 70.0 and confidence >= 75.0:
        floor -= 1.0
    return round(max(47.0, min(67.0, floor + 2.0)), 1)


def _evaluate_smart_environment(ctx: DecisionContext) -> Dict[str, Any]:
    regime = _coerce_text(getattr(ctx, 'market_regime', 'UNKNOWN'))
    volatility = _coerce_text(getattr(ctx, 'volatility', 'NORMAL'))
    trend_strength = _coerce_float(getattr(ctx, 'trend_strength', 0.0), 0.0)
    atr_value = _coerce_float(getattr(ctx, 'atr_value', 0.0), 0.0)
    liquidity = _coerce_float(getattr(ctx, 'liquidity_alignment', 0.0), 0.0)
    quality = _coerce_float(getattr(ctx, 'quality_score', 0.0), 0.0)
    confidence = _coerce_float(getattr(ctx, 'confidence_pct', 0.0), 0.0)
    ml_score = _coerce_float(getattr(ctx, 'ml_score', 0.0), 0.0)

    mode = 'NEUTRAL'
    env_bonus = 0.0
    env_penalty = 0.0
    explanation = 'Balanced market context'

    if regime == 'TRENDING' or trend_strength >= 0.65:
        mode = 'TRENDING'
        if trend_strength >= 0.75 or ctx.smc_strength >= 6.0:
            env_bonus += 3.5
            explanation = 'Trend is strong, so trend and momentum evidence receive more weight.'
        else:
            env_bonus += 2.0
            explanation = 'Trend context is present, so momentum and structure get extra support.'
        if ctx.sweep_probability >= 70.0:
            env_penalty -= 2.0
    elif regime == 'RANGING':
        mode = 'RANGING'
        if liquidity >= 70.0 or ctx.sweep_probability >= 65.0:
            env_bonus += 3.0
            explanation = 'Range structure is active, so liquidity and reversal evidence carry more weight.'
        if ctx.smc_strength >= 6.0 and ctx.ml_score <= 38.0:
            env_penalty -= 2.0
    elif regime == 'VOLATILE' or volatility in {'HIGH', 'EXPLOSIVE'} or atr_value >= 2.2:
        mode = 'HIGH_VOLATILITY'
        env_bonus += 2.5
        explanation = 'High volatility requires stronger ATR and execution risk awareness.'
        if getattr(ctx, 'execution_grade', 'UNKNOWN') in {'C', 'D', 'UNKNOWN'}:
            env_penalty -= 3.0
    else:
        mode = 'NEUTRAL'

    if confidence >= 80.0 and quality >= 75.0:
        env_bonus += 1.0
    if ml_score <= 25.0:
        env_penalty -= 2.0
    if quality < 55.0:
        env_penalty -= 1.5

    explanation = f"SMART_DECISION: {explanation}"
    return {
        'mode': mode,
        'quality_floor': _adaptive_quality_floor(ctx),
        'env_bonus': round(env_bonus, 2),
        'env_penalty': round(env_penalty, 2),
        'explanation': explanation,
    }


def _smart_entry_classification(ctx: DecisionContext, adjusted: float, dynamic_threshold: float, smart_context: Dict[str, Any]) -> str:
    structure_strength = float(getattr(ctx, 'structure_quality', 0.0) or 0.0)
    quality = float(getattr(ctx, 'quality_score', 0.0) or 0.0)
    confidence = float(getattr(ctx, 'confidence_pct', 0.0) or 0.0)
    execution_score = float(getattr(ctx, 'execution_score', 0.0) or 0.0)
    liquidity = float(getattr(ctx, 'liquidity_alignment', 0.0) or 0.0)
    structure = float(getattr(ctx, 'structure_quality', 0.0) or 0.0)

    if structure_strength >= 80.0 and ctx.strategy == 'DAILY' and ctx.signal in {'BUY', 'SELL'}:
        if adjusted >= dynamic_threshold + 6.0:
            return 'FULL_ENTRY'
        if adjusted >= max(45.0, dynamic_threshold - 2.0):
            return 'NORMAL_ENTRY'

    if adjusted < max(45.0, smart_context['quality_floor'] - 8.0):
        return 'IGNORE'

    if adjusted < max(45.0, dynamic_threshold - 4.0):
        return 'MICRO_ENTRY'

    if quality >= 60.0 and confidence >= 60.0 and execution_score >= 60.0 and liquidity >= 60.0 and structure >= 55.0:
        if adjusted < dynamic_threshold + 1.5 or (smart_context['mode'] == 'RANGING' and ctx.ml_score <= 38.0):
            return 'REDUCED_ENTRY'

    if ctx.ml_score <= 38.0 and ctx.confidence_pct <= 75.0 and ctx.quality_score <= 75.0:
        return 'REDUCED_ENTRY'

    if quality >= 66.0 and confidence >= 67.0 and execution_score >= 66.0 and liquidity >= 67.0 and structure >= 62.0:
        if adjusted >= dynamic_threshold + 7.0:
            return 'FULL_ENTRY'

    if adjusted >= max(86.0, dynamic_threshold + 16.0) and ctx.confidence_pct >= 76.0 and ctx.quality_score >= 76.0 and ctx.execution_score >= 71.0 and ctx.liquidity_alignment >= 71.0 and ctx.structure_quality >= 66.0:
        return 'HIGH_CONVICTION_ENTRY'

    if adjusted >= dynamic_threshold + 9.0 and ctx.confidence_pct >= 66.0 and ctx.quality_score >= 69.0 and ctx.execution_score >= 66.0 and ctx.liquidity_alignment >= 66.0 and ctx.structure_quality >= 61.0:
        return 'FULL_ENTRY'

    return 'NORMAL_ENTRY'


def calculate_dynamic_penalties(ctx: DecisionContext, composite: float) -> Dict[str, Any]:
    penalties: Dict[str, float] = {}
    bonuses: Dict[str, float] = {}

    strat = (ctx.strategy or '').upper()
    execution_grade = _coerce_text(getattr(ctx, 'execution_grade', 'UNKNOWN'))
    high_execution = _is_high_execution_context(ctx)
    strong_context = _strong_context_for_penalties(ctx)
    low_atr = _is_low_atr_context(ctx)
    ml_status = _ml_model_status(ctx)

    # MTF alignment penalty — adaptive, not hardcoded.
    if ctx.mtf_strength == 0:
        penalty = -6.0
        if strong_context and high_execution and low_atr:
            penalty = -2.0
        elif high_execution and ctx.liquidity_alignment >= 70.0 and ctx.market_regime in {'RANGING', 'VOLATILE'}:
            penalty = -3.0
        penalties['MTF_NONE'] = penalty
    elif ctx.mtf_strength == 1:
        penalties['MTF_WEAK'] = -3.0
    elif ctx.mtf_strength == 3:
        bonuses['MTF_STRONG'] = +4.0

    # Daily bias soft penalty
    if ctx.daily_bias and ctx.daily_bias != 'NONE':
        if ctx.daily_bias != ctx.signal:
            if _counter_trend_reversal_ok(ctx):
                penalties['BIAS_CONFLICT'] = -1.0
                bonuses['COUNTER_TREND_REVERSAL'] = +4.0
            elif strat in BIAS_ELEVATED_PENALTY_FOR:
                penalties['BIAS_CONFLICT_ELEVATED'] = -7.0
            else:
                penalties['BIAS_CONFLICT'] = -4.0
        else:
            bonuses['BIAS_ALIGNED'] = +3.0

    # SMC strength soft
    if strat == 'SMC':
        if ctx.smc_strength >= 6:
            bonuses['SMC_STRONG'] = +5.0
        elif ctx.smc_strength >= 3:
            bonuses['SMC_OK'] = +2.0
        elif ctx.smc_strength > 0:
            penalty = -2.0
            if strong_context and high_execution and ctx.structure_quality >= 60.0:
                penalty = 0.0
            elif strong_context and high_execution:
                penalty = -1.0
            penalties['SMC_WEAK'] = penalty

    # Candle trigger / execution intelligence
    if ctx.candle_trigger_confirmed:
        bonuses['CANDLE_OK'] = +3.0
    if ctx.candle_weight >= 3:
        bonuses['CANDLE_STRONG'] = +2.0
    if low_atr and (ctx.market_regime in {'RANGING', 'UNKNOWN'} or ctx.volatility in {'LOW', 'NORMAL'}):
        bonuses['ATR_MODIFIER'] = +2.0
    if high_execution:
        bonuses['EXECUTION_INTELLIGENCE'] = +3.0
    if ctx.candle_bonus > 0:
        bonuses['CANDLE_V3_BONUS'] = round(min(float(ctx.candle_bonus), 6.0), 2)
    if ctx.candle_penalty > 0:
        penalties['CANDLE_V3_PENALTY'] = -round(min(float(ctx.candle_penalty), 8.0), 2)

    # Trend confluence and alignment
    if ctx.trend_confluence_bonus > 0:
        from core.settings import TREND_CONFLUENCE_MAX_BONUS
        bonuses['TREND_CONFLUENCE_BONUS'] = round(min(float(ctx.trend_confluence_bonus), TREND_CONFLUENCE_MAX_BONUS), 2)
    if ctx.trend_confluence_penalty > 0:
        from core.settings import TREND_CONFLUENCE_MAX_PENALTY
        penalties['TREND_CONFLUENCE_PENALTY'] = -round(min(float(ctx.trend_confluence_penalty), TREND_CONFLUENCE_MAX_PENALTY), 2)

    if ctx.mtf_alignment_mode == 'ALIGNED' and ctx.mtf_alignment_score_delta > 0:
        bonuses['MTF_TREND_ALIGNED'] = round(float(ctx.mtf_alignment_score_delta), 2)
    elif ctx.mtf_alignment_mode == 'CONFLICT' and ctx.mtf_alignment_score_delta < 0:
        penalties['MTF_TREND_CONFLICT'] = round(float(ctx.mtf_alignment_score_delta), 2)

    if ctx.quant_health_tier in ('EXCELLENT', 'GOOD'):
        bonuses['QUANT_HEALTH_STRONG'] = 3.0 if ctx.quant_health_tier == 'EXCELLENT' else 1.5
    elif ctx.quant_health_tier in ('WEAK', 'POOR'):
        penalties['QUANT_HEALTH_WEAK'] = -3.0 if ctx.quant_health_tier == 'POOR' else -1.5

    # SMC entry
    if ctx.smc_entry_confirmed:
        bonuses['SMC_ENTRY_OK'] = +4.0

    # Liquidity and structure
    if ctx.liquidity_alignment >= 60:
        bonuses['LIQ_ALIGNED'] = +3.0
    if ctx.sweep_probability >= 65:
        bonuses['SWEEP_HIGH'] = +4.0
    if ctx.structure_quality >= 65.0:
        bonuses['STRUCTURE_OK'] = +1.0

    smart_context = _evaluate_smart_environment(ctx)
    if smart_context['env_bonus'] > 0:
        bonuses['SMART_ENV'] = round(smart_context['env_bonus'], 2)
    if smart_context['env_penalty'] < 0:
        penalties['SMART_ENV'] = round(smart_context['env_penalty'], 2)

    # ML as MODIFIER
    if ml_status == 'UNAVAILABLE':
        bonuses['ML_STATUS'] = 0.0
    elif ctx.ml_score >= 70:
        bonuses['ML_HIGH'] = +5.0
    elif ctx.ml_score >= 55:
        bonuses['ML_OK'] = +2.0
    elif ctx.ml_score <= 25:
        penalties['ML_LOW'] = -6.0
    elif ctx.ml_score <= 38:
        penalties['ML_WEAK'] = -3.0

    if ctx.ml_rl_action == 'SKIP' and ctx.ml_score <= 42:
        penalties['RL_SKIP'] = -4.0

    # Recent performance
    if ctx.recent_losses >= 3:
        penalties['RECENT_LOSSES'] = -6.0
    elif ctx.recent_losses >= 2:
        penalties['RECENT_LOSSES_MILD'] = -3.0

    if ctx.recent_wr >= 0.60:
        bonuses['WR_HOT'] = +3.0

    # RR ratio / spread / crisis
    if ctx.rr_ratio >= 2.0:
        bonuses['RR_EXCELLENT'] = +4.0
    elif ctx.rr_ratio >= 1.5:
        bonuses['RR_GOOD'] = +2.0
    elif ctx.rr_ratio < 1.0 and ctx.rr_ratio > 0:
        penalties['RR_LOW'] = -3.0

    if 0.30 < ctx.spread_ratio <= 0.50:
        penalties['SPREAD_HIGH'] = -3.0

    if ctx.crisis_active and ctx.strategy in ('DAILY', 'SMC'):
        penalties['CRISIS_ACTIVE'] = -8.0

    if high_execution:
        for key in ('MTF_NONE', 'MTF_WEAK', 'SMC_WEAK', 'ML_WEAK', 'ML_LOW', 'RL_SKIP', 'RECENT_LOSSES_MILD', 'SPREAD_HIGH'):
            if key in penalties and penalties[key] < 0:
                penalties[key] = max(penalties[key] + 1.0, -1.0)

    # SMC V3 layer
    try:
        from core.smc_v3_integration import compute_smc_v3_layer
        from core.settings import SMC_V3_BONUS_CAP, SMC_V3_BONUS_FLOOR

        rates = getattr(ctx, 'rates', None) if hasattr(ctx, 'rates') else None
        smc_v3 = compute_smc_v3_layer(
            symbol=getattr(ctx, 'symbol', 'XAUUSD'),
            signal=getattr(ctx, 'signal', '') or '',
            rates=rates,
        )
        smc_bonus = float(smc_v3.get('smc_v3_bonus', 0))
        if smc_bonus >= 3:
            bonuses['SMC_V3_STRONG'] = +round(min(smc_bonus, SMC_V3_BONUS_CAP), 2)
        elif smc_bonus >= 1:
            bonuses['SMC_V3_OK'] = +round(smc_bonus, 2)
        elif smc_bonus < 0:
            penalties['SMC_V3_WEAK'] = round(max(smc_bonus, SMC_V3_BONUS_FLOOR), 2)
    except Exception as e:
        print(f'⚠️ SMC_V3 layer failed: {e}')

    total_penalty = sum(penalties.values())
    total_bonus = sum(bonuses.values())
    adjusted = composite + total_bonus + total_penalty

    return {
        'penalties': penalties,
        'bonuses': bonuses,
        'total_penalty': round(total_penalty, 2),
        'total_bonus': round(total_bonus, 2),
        'adjusted_composite': round(adjusted, 2),
    }


def _apply_soft_modifiers(ctx: DecisionContext, composite: float) -> Dict[str, Any]:
    return calculate_dynamic_penalties(ctx, composite)


def _resolve_decision(adjusted: float, ctx: DecisionContext) -> Dict[str, Any]:
    dynamic_threshold = calculate_dynamic_entry_threshold(ctx)
    micro_threshold = max(45.0, min(50.0, dynamic_threshold - 4.0))
    reduced_threshold = max(45.0, min(55.0, dynamic_threshold - 2.0))
    full_threshold = max(48.0, min(65.0, dynamic_threshold))
    smart_context = _evaluate_smart_environment(ctx)
    classification = _smart_entry_classification(ctx, adjusted, dynamic_threshold, smart_context)

    crisis_cap_micro = ctx.crisis_active and ctx.strategy in ('DAILY', 'SMC')
    counter_trend_cap_micro = _counter_trend_reversal_ok(ctx)

    if classification == 'IGNORE' or adjusted < micro_threshold:
        return {
            'decision': 'HARD_BLOCK',
            'size_mode': 'NONE',
            'risk_multiplier': 0.0,
            'reason': f'IGNORE:{adjusted:.1f}<{micro_threshold:.1f}',
            'classification': classification,
            'smart_context': smart_context,
        }

    if classification == 'MICRO_ENTRY' or adjusted < reduced_threshold or crisis_cap_micro or counter_trend_cap_micro:
        if ctx.quality_score < 60.0 or ctx.confidence_pct < 60.0:
            return {
                'decision': 'HARD_BLOCK',
                'size_mode': 'NONE',
                'risk_multiplier': 0.0,
                'reason': f'WEAK_SIGNAL_BLOCK:{adjusted:.1f}',
                'classification': classification,
                'smart_context': smart_context,
            }
        return {
            'decision': 'PASS_MICRO',
            'size_mode': 'MICRO',
            'risk_multiplier': 0.30 if crisis_cap_micro else 0.40 if counter_trend_cap_micro else 0.50,
            'reason': f'MICRO_PATH:{adjusted:.1f}',
            'classification': classification,
            'smart_context': smart_context,
        }

    if classification == 'REDUCED_ENTRY' or adjusted < full_threshold:
        if ctx.quality_score < 60.0 or ctx.confidence_pct < 60.0:
            return {
                'decision': 'HARD_BLOCK',
                'size_mode': 'NONE',
                'risk_multiplier': 0.0,
                'reason': f'WEAK_SIGNAL_BLOCK:{adjusted:.1f}',
                'classification': classification,
                'smart_context': smart_context,
            }
        return {
            'decision': 'PASS_REDUCED',
            'size_mode': 'REDUCED',
            'risk_multiplier': 0.70,
            'reason': f'REDUCED_PATH:{adjusted:.1f}',
            'classification': classification,
            'smart_context': smart_context,
        }

    if classification == 'FULL_ENTRY':
        return {
            'decision': 'PASS_FULL',
            'size_mode': 'FULL',
            'risk_multiplier': 1.10,
            'reason': f'FULL_PATH:{adjusted:.1f}',
            'classification': classification,
            'smart_context': smart_context,
        }

    if classification == 'HIGH_CONVICTION_ENTRY':
        return {
            'decision': 'PASS_FULL',
            'size_mode': 'FULL',
            'risk_multiplier': 1.20,
            'reason': f'PREMIUM_FULL:{adjusted:.1f}',
            'classification': classification,
            'smart_context': smart_context,
        }

    return {
        'decision': 'PASS_FULL',
        'size_mode': 'FULL',
        'risk_multiplier': 1.00,
        'reason': f'FULL_PATH:{adjusted:.1f}',
        'classification': classification,
        'smart_context': smart_context,
    }


def unified_decide(ctx: DecisionContext) -> DecisionResult:
    result = DecisionResult()

    block_reason = _hard_block_check(ctx)
    if block_reason:
        result.decision = 'HARD_BLOCK'
        result.size_mode = 'NONE'
        result.risk_multiplier = 0.0
        result.hard_block_reason = block_reason
        result.reasons.append(f'HARD_BLOCK:{block_reason}')
        return result

    composite_data = _calc_composite(ctx)
    composite = composite_data['composite']

    mods = _apply_soft_modifiers(ctx, composite)
    result.penalties = mods['penalties']
    result.bonuses = mods['bonuses']
    adjusted = mods['adjusted_composite'] + float(ctx.legacy_score_adjustment or 0)

    if ctx.legacy_score_adjustment:
        result.debug['legacy_score_adjustment'] = float(ctx.legacy_score_adjustment)

    res = _resolve_decision(adjusted, ctx)
    result.decision = res['decision']
    result.size_mode = res['size_mode']
    result.risk_multiplier = res['risk_multiplier']
    result.composite_score = adjusted
    result.reasons.append(res['reason'])
    if res.get('classification'):
        result.reasons.append(f'SMART_DECISION:{res["classification"]}')

    if TESTING_MODE:
        quota = test_mode_can_allocate(size_mode=result.size_mode)
        result.debug['test_mode_quota'] = quota
        if not quota['allowed']:
            result.decision = 'HARD_BLOCK'
            result.size_mode = 'NONE'
            result.risk_multiplier = 0.0
            result.hard_block_reason = quota['reason']
            result.reasons.append(f'HARD_BLOCK:{quota["reason"]}')
            return result

    result.debug = {
        'raw_composite': composite,
        'dynamic_threshold': calculate_dynamic_entry_threshold(ctx),
        'execution_grade': getattr(ctx, 'execution_grade', 'UNKNOWN'),
        'execution_score': getattr(ctx, 'execution_score', 0.0),
        'ml_status': _ml_model_status(ctx),
        'sub_scores': {
            'quality': composite_data['quality'],
            'confidence': composite_data['confidence'],
            'brain': composite_data['brain'],
            'execution': composite_data['execution'],
            'context': composite_data['context'],
        },
        'total_bonus': mods['total_bonus'],
        'total_penalty': mods['total_penalty'],
        'adjusted': adjusted,
        'strategy': ctx.strategy,
        'signal': ctx.signal,
        'session': ctx.session,
        'regime': ctx.market_regime,
        'counter_trend_active': _counter_trend_reversal_ok(ctx),
        'smart_entry_classification': res.get('classification', 'NORMAL_ENTRY'),
        'smart_quality_floor': res.get('smart_context', {}).get('quality_floor', 0.0),
        'smart_market_mode': res.get('smart_context', {}).get('mode', 'NEUTRAL'),
        'smart_explanation': res.get('smart_context', {}).get('explanation', 'Balanced market context'),
    }
    return result


def format_decision_log(result: DecisionResult) -> str:
    icons = {
        'HARD_BLOCK':   '🚫',
        'PASS_FULL':    '🟢',
        'PASS_REDUCED': '🟡',
        'PASS_MICRO':   '🔵',
    }
    icon = icons.get(result.decision, '⚪')
    base = f'{icon} UNIFIED: {result.decision} | Score:{result.composite_score:.1f} | Risk×{result.risk_multiplier:.2f} | {result.size_mode}'
    if result.hard_block_reason:
        return f'{base} | {result.hard_block_reason}'

    dynamic_threshold = result.debug.get('dynamic_threshold', 0.0)
    execution_grade = result.debug.get('execution_grade', 'UNKNOWN')
    execution_bonus = sum(v for k, v in result.bonuses.items() if k == 'EXECUTION_INTELLIGENCE')
    atr_modifier = sum(v for k, v in result.bonuses.items() if k == 'ATR_MODIFIER')
    liquidity_bonus = sum(v for k, v in result.bonuses.items() if k == 'LIQ_ALIGNED')
    candle_bonus = sum(v for k, v in result.bonuses.items() if k in {'CANDLE_OK', 'CANDLE_STRONG', 'CANDLE_V3_BONUS'})
    structure_bonus = sum(v for k, v in result.bonuses.items() if k == 'STRUCTURE_OK')
    ml_penalty = sum(v for k, v in result.penalties.items() if k.startswith('ML'))
    mtf_penalty = result.penalties.get('MTF_NONE', result.penalties.get('MTF_WEAK', 0.0))
    smc_penalty = result.penalties.get('SMC_WEAK', 0.0)
    recent_loss_penalty = result.penalties.get('RECENT_LOSSES', result.penalties.get('RECENT_LOSSES_MILD', 0.0))

    smart_classification = result.debug.get('smart_entry_classification', 'NORMAL_ENTRY')
    smart_explanation = result.debug.get('smart_explanation', 'Balanced market context')
    final_decision = 'EXECUTE' if result.decision != 'HARD_BLOCK' else 'BLOCK'
    return '\n'.join([
        '==========================',
        'SMART DECISION AUTHORITY',
        '==========================',
        f'Dynamic Threshold : {dynamic_threshold:.1f}',
        f'Composite Score : {result.composite_score:.1f}',
        f'Execution Grade : {execution_grade}',
        f'Execution Bonus : {execution_bonus:+.0f}',
        f'ATR Modifier : {atr_modifier:+.0f}',
        f'Liquidity Bonus : {liquidity_bonus:+.0f}',
        f'Candle Bonus : {candle_bonus:+.0f}',
        f'Structure Bonus : {structure_bonus:+.0f}',
        f'ML Penalty : {ml_penalty:.0f}',
        f'MTF Penalty : {mtf_penalty:.0f}',
        f'SMC Penalty : {smc_penalty:.0f}',
        f'Recent Loss Penalty : {recent_loss_penalty:.0f}',
        f'Smart Entry Classification : {smart_classification}',
        f'Final Decision : {final_decision}',
        f'Reason : {smart_explanation}',
        '==========================',
    ])