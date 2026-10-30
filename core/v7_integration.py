# =========================================
# FER3ON V7 — INTEGRATION LAYER
# Wires V7 + Recovery+ modules into main trading pipeline
# =========================================

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.settings import (
    V7_ENABLED,
    V7_PLUS_ENABLED,
    V7_VACUUM_EXEC_BONUS,
    V7_MICRO_TRIGGER_REQUIRED,
    V7_RECOVERY_MAX_TOTAL_BONUS,
    V7_DASHBOARD_UPDATE_INTERVAL,
)
from core.dynamic_confidence import get_dynamic_confidence_threshold
from core.velocity_engine import analyze_velocity_from_closes
from core.sweep_predictor import compute_sweep_probability
from core.liquidity_vacuum import analyze_liquidity_vacuum
from core.confidence_decay import setup_decay_tracker
from core.missed_opportunity import (
    record_rejection,
    evaluate_pending,
    get_missed_opportunity_score,
    get_missed_opportunity_stats,
    get_evaluated_records,
)
from core.micro_trigger import check_micro_trigger, candle_value, _no_candles
from core.candle_context import analyze_candle_context
from core.session_intelligence import analyze_session_intelligence
from brain.opportunity_engine import evaluate_opportunity
from brain.smc_arbitration import analyze_smc_arbitration
from brain.filter_relaxation import (
    analyze_filter_relaxation,
    apply_threshold_relaxation,
    sync_false_rejections_from_missed_opportunity,
)
from risk.hard_risk_cap import check_hard_risk_cap, cap_risk_percent, record_trade_loss
from analytics.recovery_dashboard import update_recovery_dashboard, record_recovery_trade
from execution.scale_in import evaluate_scale_in, confidence_to_scale_pct


def v7_enabled():
    return bool(V7_ENABLED)


def v7_plus_enabled():
    return bool(V7_ENABLED and V7_PLUS_ENABLED)


_last_dashboard_update = 0.0


def run_v7_recovery_plus_analysis(
    smc_signal,
    smc_strength,
    signal,
    daily_bias,
    structure_bias,
    liquidity_bias,
    mtf_direction,
    smc_patterns=None,
    buy_score=None,
    sell_score=None,
    hour=0,
    strategy="UNKNOWN",
    session="UNKNOWN",
    market_regime="UNKNOWN",
):
    """Run Recovery+ modules: SMC arbitration, filter relaxation, session intel."""
    if not v7_plus_enabled():
        return _empty_recovery_plus_context()

    mo_stats = get_missed_opportunity_stats()
    sync_false_rejections_from_missed_opportunity(get_evaluated_records())

    smc_arb = analyze_smc_arbitration(
        smc_signal=smc_signal,
        smc_strength=smc_strength,
        signal=signal,
        daily_bias=daily_bias,
        structure_bias=structure_bias,
        liquidity_bias=liquidity_bias,
        mtf_direction=mtf_direction,
        smc_patterns=smc_patterns,
        buy_score=buy_score,
        sell_score=sell_score,
    )

    filter_relax = analyze_filter_relaxation(
        false_rejection_rate=mo_stats.get("false_rejection_rate", 0),
        missed_opportunity_score=mo_stats.get("missed_opportunity_score", 50),
        strategy=strategy,
        session=session,
        regime=market_regime,
    )

    session_intel = analyze_session_intelligence(hour, signal=signal)

    recovery_bonus = min(
        float(V7_RECOVERY_MAX_TOTAL_BONUS),
        float(smc_arb.get("confidence_bonus", 0) or 0)
        + float(session_intel.get("confidence_modifier", 0) or 0),
    )

    return {
        "smc_arbitration": smc_arb,
        "filter_relaxation": filter_relax,
        "session_intelligence": session_intel,
        "recovery_confidence_bonus": round(recovery_bonus, 2),
        "conflict_penalty_reduction": float(
            smc_arb.get("conflict_penalty_reduction", 0) or 0
        ),
    }


def apply_recovery_plus_confidence(
    base_confidence_pct,
    recovery_plus_context,
):
    """Apply capped Recovery+ confidence bonus."""
    if not v7_plus_enabled():
        return float(base_confidence_pct or 0)
    bonus = float(recovery_plus_context.get("recovery_confidence_bonus", 0) or 0)
    return round(float(base_confidence_pct or 0) + bonus, 2)


def apply_recovery_plus_threshold(
    threshold,
    recovery_plus_context,
):
    """Apply filter relaxation and session threshold modifiers."""
    if not v7_plus_enabled() or threshold is None:
        return threshold

    relax = recovery_plus_context.get("filter_relaxation", {})
    factor = float(relax.get("filter_relaxation_factor", 1.0) or 1.0)
    relaxed = apply_threshold_relaxation(float(threshold), factor)

    session_intel = recovery_plus_context.get("session_intelligence", {})
    thresh_mod = float(session_intel.get("threshold_modifier", 0) or 0)
    return round(max(0.0, relaxed + thresh_mod), 2)


def check_recovery_hard_risk(account_balance, requested_risk_percent=0.0, daily_loss=None):
    """Hard risk cap check — returns status dict."""
    if not v7_plus_enabled():
        return {
            "enabled": False,
            "allowed": True,
            "hard_risk_status": "ACTIVE",
            "capped_risk_percent": float(requested_risk_percent or 0),
        }
    return check_hard_risk_cap(account_balance, requested_risk_percent, daily_loss)


def cap_recovery_risk(requested_risk_percent):
    """Cap per-trade risk via hard risk module."""
    if not v7_plus_enabled():
        return float(requested_risk_percent or 0)
    return cap_risk_percent(requested_risk_percent)


def apply_recovery_session_risk(base_risk_percent, recovery_plus_context):
    """Apply session risk modifier."""
    if not v7_plus_enabled():
        return float(base_risk_percent or 0)
    mod = float(
        recovery_plus_context.get("session_intelligence", {}).get("risk_modifier", 1.0)
        or 1.0
    )
    return round(float(base_risk_percent or 0) * mod, 4)


def maybe_update_recovery_dashboard(force=False):
    """Periodically refresh RECOVERY_METRICS.json and dashboard."""
    import time as _time

    global _last_dashboard_update
    if not v7_plus_enabled():
        return None

    now = _time.time()
    if not force and (now - _last_dashboard_update) < V7_DASHBOARD_UPDATE_INTERVAL:
        return None

    _last_dashboard_update = now
    return update_recovery_dashboard(get_missed_opportunity_stats())


def _empty_recovery_plus_context():
    return {
        "smc_arbitration": {"enabled": False, "confidence_bonus": 0.0},
        "filter_relaxation": {"enabled": False, "filter_relaxation_factor": 1.0},
        "session_intelligence": {"enabled": False, "confidence_modifier": 0.0},
        "recovery_confidence_bonus": 0.0,
        "conflict_penalty_reduction": 0.0,
    }


def process_missed_opportunities(symbol):
    """Call each main-loop iteration to evaluate pending rejections."""

    def _price(sym):
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            return 0.0
        return (tick.ask + tick.bid) / 2

    if not v7_enabled():
        return {"evaluated": 0, "stats": {}}
    return evaluate_pending(symbol, _price)


def run_v7_market_analysis(symbol, rates, atr, signal, session, mtf_direction, mtf_strength, liquidity_data, liq_map):
    """Compute V7 modifiers from market data (no MT5 order impact)."""
    if not v7_enabled():
        return _empty_v7_context()

    if _no_candles(rates):
        return _empty_v7_context()

    closes = [float(candle_value(c, "close", 0)) for c in rates]
    candles = list(rates)

    mtf_aligned = mtf_direction == signal and signal in ("BUY", "SELL")

    velocity = analyze_velocity_from_closes(closes, atr)

    vacuum = analyze_liquidity_vacuum(candles, closes, atr, mtf_aligned=mtf_aligned)

    candle_ctx = analyze_candle_context(candles, signal)

    pools = []
    if isinstance(liq_map, dict):
        pools = (liq_map.get("pools_above") or []) + (liq_map.get("pools_below") or [])

    price = closes[-1] if closes else 0.0
    sweep = compute_sweep_probability(
        signal=signal,
        equal_highs=liquidity_data.get("equal_highs", []) if liquidity_data else [],
        equal_lows=liquidity_data.get("equal_lows", []) if liquidity_data else [],
        liquidity_pools=pools,
        current_price=price,
        session=session,
        distance_to_pool=liq_map.get("distance_next") if isinstance(liq_map, dict) else None,
    )

    total_bonus = (
        velocity.get("confidence_bonus", 0)
        + sweep.get("confidence_bonus", 0)
        + candle_ctx.get("confidence_bonus", 0)
    )
    exec_bonus = V7_VACUUM_EXEC_BONUS if vacuum.get("fast_execution_eligible") else 0.0

    return {
        "velocity": velocity,
        "vacuum": vacuum,
        "sweep": sweep,
        "candle_context": candle_ctx,
        "confidence_bonus": round(total_bonus, 2),
        "execution_bonus": exec_bonus,
        "mtf_aligned": mtf_aligned,
        "fast_execution_eligible": vacuum.get("fast_execution_eligible", False),
        "candle_weight_bonus": candle_ctx.get("weight_bonus", 0),
    }


def apply_v7_confidence_adjustments(base_confidence_pct, strategy, signal, symbol, atr, session, v7_context):
    """Apply bonuses and decay → adjusted confidence for gating."""
    if not v7_enabled():
        return {
            "adjusted_confidence": float(base_confidence_pct or 0),
            "decay": {"enabled": False},
            "bonus_applied": 0.0,
        }

    bonus = float(v7_context.get("confidence_bonus", 0) or 0)
    boosted = float(base_confidence_pct or 0) + bonus

    decay = setup_decay_tracker.get_decayed_confidence(
        strategy=strategy,
        signal=signal,
        symbol=symbol,
        initial_confidence=boosted,
        atr=atr,
        session=session,
    )

    return {
        "adjusted_confidence": decay["decayed_confidence"],
        "decay": decay,
        "bonus_applied": bonus,
        "boosted_before_decay": round(boosted, 2),
    }


def get_v7_dynamic_threshold(session, market_regime, hour):
    if not v7_enabled():
        from core.settings import QUALITY_CONFIDENCE_BYPASS
        return QUALITY_CONFIDENCE_BYPASS
    return get_dynamic_confidence_threshold(session, market_regime, hour)["threshold"]


def handle_final_brain_rejection(
    verdict,
    symbol,
    strategy,
    signal,
    confidence_pct,
    setup_score,
    regime,
    session,
    liquidity_bias,
    structure_bias,
    entry_price,
    mtf_direction,
    market_regime,
    hour,
    risk_blocked=False,
    crisis_active=False,
    rejection_reason="FINAL_BRAIN",
):
    """
    On WAIT/REJECT: record missed opportunity and try opportunistic entry.
    Returns opportunistic result or None.
    """
    if not v7_enabled():
        return None

    if verdict in ("WAIT", "REJECT"):
        record_rejection(
            symbol=symbol,
            strategy=strategy,
            direction=signal,
            confidence=confidence_pct,
            setup_score=setup_score,
            regime=regime,
            session=session,
            liquidity_bias=liquidity_bias,
            structure_bias=structure_bias,
            entry_price=entry_price,
            verdict=verdict,
            rejection_reason=rejection_reason,
        )

    opp = evaluate_opportunity(
        signal=signal,
        confidence_pct=confidence_pct,
        mtf_direction=mtf_direction,
        liquidity_bias=liquidity_bias,
        session=session,
        market_regime=market_regime,
        hour=hour,
        risk_blocked=risk_blocked,
        crisis_active=crisis_active,
    )

    if opp.get("action") in ("ENTER_QUARTER", "ENTER_HALF"):
        return opp
    return None


def check_v7_micro_trigger(symbol, signal):
    if not v7_enabled():
        return {
            "confirmed": True,
            "micro_trigger_confirmed": True,
            "score": 100,
            "enabled": False,
        }

    try:
        m1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 30)
        if m1 is None:
            return {
                "confirmed": not V7_MICRO_TRIGGER_REQUIRED,
                "micro_trigger_confirmed": not V7_MICRO_TRIGGER_REQUIRED,
                "score": 0,
                "reason": "NO_M1_DATA",
                "enabled": True,
            }
        return check_micro_trigger(list(m1), signal)
    except Exception as e:
        print(f"[MICRO] ERROR: {e}")
        return {
            "confirmed": False,
            "micro_trigger_confirmed": False,
            "score": 0,
            "reason": "MICRO_TRIGGER_ERROR",
            "enabled": True,
        }


def compute_v7_final_brain_bonus(v7_context):
    if not v7_enabled():
        return 0.0
    bonus = float(v7_context.get("execution_bonus", 0) or 0)
    if v7_context.get("fast_execution_eligible"):
        print(f"[V7] FAST_EXEC_BONUS: +{bonus}")
    return bonus


def apply_v7_initial_entry_scale(confidence_pct, base_lot):
    """Apply confidence-based initial scale (55–64 → 25%, etc.)."""
    if not v7_enabled():
        return base_lot, 1.0, "V7_DISABLED"
    scale = confidence_to_scale_pct(confidence_pct)
    if scale <= 0 or scale >= 1.0:
        return base_lot, 1.0, "FULL_SIZE"
    scaled = round(max(0.01, base_lot * scale), 2)
    return scaled, scale, f"V7_SCALE_{int(scale * 100)}PCT"


def run_v7_scale_in_for_positions(positions, symbol, confidence_pct, risk_blocked=False):
    """Evaluate scale-in for open winning positions."""
    if not v7_enabled() or not positions:
        return []

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return []
    mid = (tick.ask + tick.bid) / 2
    plans = []

    for pos in positions:
        plan = evaluate_scale_in(
            position=pos,
            current_price=mid,
            confidence_score=confidence_pct,
            risk_blocked=risk_blocked,
            already_scaled=False,
            base_lot=float(getattr(pos, "volume", 0.01) or 0.01),
        )
        if plan.get("approved"):
            plan["ticket"] = getattr(pos, "ticket", None)
            plans.append(plan)
    return plans


def clear_setup_decay(strategy, signal, symbol):
    setup_decay_tracker.clear(strategy, signal, symbol)


def get_v7_status_summary():
    return {
        "enabled": v7_enabled(),
        "plus_enabled": v7_plus_enabled(),
        "missed_opportunity_score": get_missed_opportunity_score(),
    }


def _empty_v7_context():
    return {
        "velocity": {},
        "vacuum": {},
        "sweep": {},
        "confidence_bonus": 0.0,
        "execution_bonus": 0.0,
        "mtf_aligned": False,
        "fast_execution_eligible": False,
        "candle_weight_bonus": 0,
    }
