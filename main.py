import os
import sys
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from core.env_utils import load_project_env

load_project_env(__file__)

from core.main_helpers import (
    build_market_snapshot_hash as _build_market_snapshot_hash,
    derive_signal as _derive_signal_helper,
    get_rate_close as _get_rate_close_helper,
    rates_to_candles as _rates_to_candles_helper,
    smc_strength_from_details as _smc_strength_from_details_helper,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(os.getcwd())))

from certification.framework import update_certification_progress
from core.analytics import analyze_trades, write_daily_performance_report
from core.atr_manager import calculate_atr
from core.candle_trigger import check_candle_trigger
from core.confidence_engine import get_confidence_v2
from core.execution_intelligence import execute_intelligence_check
from core.fer3on_decision_authority import (
    build_decision_context,
    decide_trade,
    decision_to_runtime_format,
    format_authority_log,
)

# =============================================================================
# PHASE 2 — Unified Decision Authority for the primary entry path
# =============================================================================
try:
    from core.phase2_unified_authority import get_unified_authority
    _PHASE2_AUTHORITY_AVAILABLE = True
except Exception as _phase2_import_err:
    _PHASE2_AUTHORITY_AVAILABLE = False
    print(f"[PHASE2] Authority import warning: {_phase2_import_err}")

# =============================================================================
# PHASE 5 — Opportunity Allocator (Gradual Sizing)
# Ranks opportunities EXCELLENT→GOOD→FAIR→WEAK for selective sizing
# =============================================================================
try:
    from core.opportunity_allocator import (
        rank_opportunity,
        apply_sizing,
        effective_risk_adjustment,
    )
    _PHASE5_ALLOCATOR_AVAILABLE = True
except Exception as _phase5_import_err:
    _PHASE5_ALLOCATOR_AVAILABLE = False
    print(f"[PHASE5] Opportunity allocator import warning: {_phase5_import_err}")
from core.market_regime import detect_market_regime
from core.market_structure import get_market_structure
from core.professional_swing_structure import (
    analyze_swing_structure,
    build_swing_structure_report,
    evaluate_entry_readiness,
    select_structural_targets,
)
from core.mt5_compat import MT5_AVAILABLE, connect_mt5, mt5
from core.mt5_history_sync import sync_mt5_history
from analytics.csv_truth_bridge import sync_csv_to_truth_layer
from analytics.execution_quality import calculate_execution_quality_score, calculate_regime_fit_score
from core.quality_score import evaluate_quality_gate
from core.risk_manager import calculate_smart_lot, evaluate_position_limits, get_loss_limits_status, compute_realized_risk_percent
from core.news_filter import is_news_active
from core.session_intelligence import (
    compute_session_intelligence_score,
    detect_session_phase,
    get_session,
    get_session_confidence,
)
from core.settings import (
    CHECK_INTERVAL, DAILY_MAGIC, DAILY_RUNTIME_ENABLED, SMC_MAGIC, SYMBOL, TESTING_MODE_LOT_CAPS, MAX_DAILY_TRADES,
    BASE_ACCOUNT_BALANCE, MAX_LOT, TRADE_COOLDOWN, ASIA_TRADING_ENABLED,
    OFF_HOURS_MAX_TRADES,
    LONDON_VOLATILE_BLOCK_ENABLED, LONDON_VOLATILE_START, LONDON_VOLATILE_END,
    MAX_SAME_DIRECTION_POSITIONS,
    PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED,
    RISK_PER_TRADE_PERCENT, MIN_EFFECTIVE_RISK_PERCENT, MAX_RISK_TOTAL,
    BREAKEVEN_BUFFER_ATR, MULTI_TP_PROFILE,
    SHADOW_ONLY_RUNTIME, SHADOW_RUN_MAX_CYCLES,
    HISTORY_DIR,
    PROACTIVE_OPPORTUNITY_SCAN_ENABLED,
    PROACTIVE_OPPORTUNITY_SCAN_INTERVAL,
    TP_ATR_CAP_MULT, TP_SL_MULT,
    get_tp_cap_multiplier, get_tp_sl_multiplier,
    get_min_sl_dollars,
)
from core.portfolio_risk_authority import (
    evaluate_risk,
    record_trade_open,
    record_trade_close,
    reconcile_with_live_positions,
    sync_portfolio_equity,
)
from core.startup_check import run_startup_check
from core.test_mode_manager import get_quota_state
from core.trade_executor import execute_trade, get_filled_volume
from core.adaptive_sl_tp_engine import calculate_adaptive_sl_tp
from core.position_manager import manage_open_positions
from core.loss_pause_guard import (
    evaluate_loss_pause,
    register_trade_result as register_loss_pause_result,
    get_status as get_loss_pause_status,
)
from core.watchdog import run_watchdog_cycle
from core.telegram_bot import check_telegram_health
from core.trade_identity import strategy_from_magic

# =============================================================================
# 🌑 SHADOW LEARNING ENGINE + 🎯 MULTI-REGIME ANALYZER
# Advanced Learning from Rejected Signals + Context-Aware Strategy Selection
# =============================================================================
try:
    from analytics.shadow_learning_engine import ShadowLearningEngine, should_apply_shadow_learning
    _SHADOW_LEARNING_AVAILABLE = True
except Exception as _shadow_learning_err:
    _SHADOW_LEARNING_AVAILABLE = False
    print(f"[SHADOW LEARNING] Import warning: {_shadow_learning_err}")

try:
    from core.multi_regime_analyzer import MultiDimensionalRegimeAnalyzer
    _MULTI_REGIME_AVAILABLE = True
except Exception as _multi_regime_err:
    _MULTI_REGIME_AVAILABLE = False
    print(f"[MULTI-REGIME] Import warning: {_multi_regime_err}")

try:
    from core.v7_integration import process_missed_opportunities
    _MISSED_OPPORTUNITY_AVAILABLE = True
except Exception as _missed_opp_err:
    _MISSED_OPPORTUNITY_AVAILABLE = False
    print(f"[MISSED-OPPORTUNITY] Import warning: {_missed_opp_err}")

from ml.feature_engine import extract_live_features
from ml.ml_orchestrator import ml_evaluate_trade
from brain.master_brain import get_master_score
from core.liquidity_intelligence import get_liquidity_bias
from core.smc_entry_engine import check_smc_entry_sequence

# =============================================================================
# SMART COUNTER-TRADING ENGINE
# [FER3ON-FIX-2026-09-02]
# Opportunistic position taking when strong signal bias detected
# =============================================================================
try:
    from core.smart_counter_trading import (
        should_apply_smart_counter_trading,
        get_counter_position,
        log_counter_trade,
        get_counter_trading_summary,
    )
    _SMART_COUNTER_AVAILABLE = True
except Exception as _smart_counter_err:
    _SMART_COUNTER_AVAILABLE = False
    print(f"[SMART-COUNTER] Import warning (non-fatal): {_smart_counter_err}")

# =============================================================================
# PHASE 1B/1E — Signal Snapshot Bridge (Unified for ALL Strategies)
# Converts dict-based signals to SignalSnapshot contracts (non-breaking)
# Supports the active SMC and DAILY strategies.
# =============================================================================
try:
    from core.phase1b_main_bridge import UnifiedStrategyBridge
    _BRIDGE_AVAILABLE = True
except Exception as _bridge_import_err:
    _BRIDGE_AVAILABLE = False
    print(f"[PHASE1E] Bridge import warning: {_bridge_import_err}")

unified_bridge = None

# =============================================================================
# PHASE 3 — Institutional Shadow Architecture
# Sidecar import — safe lazy load. Never blocks runtime if Phase 3 missing.
# =============================================================================
try:
    from core.settings import PHASE3_ENABLED as _PHASE3_ENABLED
    if _PHASE3_ENABLED:
        from core.phase3.phase3_orchestrator import (
            Phase3Input,
            run_phase3_shadow,
            notify_trade_closed as _phase3_notify_trade_closed,
            get_phase3_status as _get_phase3_status,
        )
        _PHASE3_AVAILABLE = True
        print("[PHASE3] Shadow architecture loaded — ADVISORY MODE ONLY")
    else:
        _PHASE3_AVAILABLE = False
        print("[PHASE3] Disabled in settings")
except Exception as _phase3_import_err:
    _PHASE3_AVAILABLE = False
    print(f"[PHASE3] Import skipped (non-fatal): {_phase3_import_err}")

# Track last Phase 3 shadow decision for trade-close correlation
_last_phase3_shadow_decision: str = "UNKNOWN"
_last_phase3_ml_timestamp: float = 0.0

# =============================================================================
# FAIE — Phase-2 spec §5: Shadow-Logging Call Site
# (docs/FAIE/PHASE_2_SPECIFICATION.md §5 — distinct from the "PHASE 3"
# Institutional Shadow Architecture above, which is an unrelated sidecar.)
# Sidecar import — enabled by default, with a per-run environment override.
# Missing FAIE code or a disabled setting never blocks the runtime.
# =============================================================================
try:
    from core.settings import FAIE_SHADOW_LOGGING_ENABLED as _FAIE_SHADOW_LOGGING_ENABLED
    if _FAIE_SHADOW_LOGGING_ENABLED:
        from brain.faie import log_faie_shadow_decision as _log_faie_shadow_decision
        _FAIE_SHADOW_AVAILABLE = True
        print("[FAIE] Shadow logging enabled — ADVISORY/LOGGING ONLY, see docs/FAIE/PHASE_2_SPECIFICATION.md §5")
    else:
        _FAIE_SHADOW_AVAILABLE = False
except Exception as _faie_import_err:
    _FAIE_SHADOW_AVAILABLE = False
    print(f"[FAIE] Shadow logging import skipped (non-fatal): {_faie_import_err}")


def build_market_snapshot_hash(rates, atr, market_regime, session, confidence_pct):
    return _build_market_snapshot_hash(rates, atr, market_regime, session, confidence_pct)


_last_analysis_hash = None
_last_analysis_time = 0.0
_resolver_candles_cache = []

# =============================================================================
# V3.5 PHASE-1 FIX: real per-strategy cooldown tracking.
# Previously `cooldown_active=False` was hardcoded in build_decision_context(),
# meaning the COOLDOWN_ACTIVE hard-block in unified_decision.py could never
# fire and TRADE_COOLDOWN (settings.py) was never actually read anywhere.
# =============================================================================
_last_trade_time: dict = {}  # strategy -> unix timestamp of last opened trade
_logged_exit_actions: set[tuple[int, str, str]] = set()
_virtual_shadow_seen: set[str] = set()
_virtual_shadow_failed: set[str] = set()
_off_hours_lock = threading.RLock()


def _cooldown_active_for(strategy: str) -> bool:
    last = _last_trade_time.get(str(strategy or '').upper(), 0.0)
    return (time.time() - last) < TRADE_COOLDOWN


def _register_trade_opened(strategy: str) -> None:
    _last_trade_time[str(strategy or '').upper()] = time.time()


# V3.5 PHASE-1: OFF_HOURS daily trade cap — separate from cooldown, counts
# trades opened during the OFF_HOURS session and resets at UTC day rollover.
_off_hours_trade_count = 0
_off_hours_count_day: Optional[str] = None


def _off_hours_cap_hit() -> bool:
    """Check if off-hours cap is hit. Thread-safe."""
    global _off_hours_trade_count, _off_hours_count_day
    with _off_hours_lock:  # HIGH FIX #7: Lock before accessing shared state
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if _off_hours_count_day != today:
            _off_hours_count_day = today
            _off_hours_trade_count = 0
        return _off_hours_trade_count >= OFF_HOURS_MAX_TRADES


def _register_off_hours_trade() -> None:
    """Register an off-hours trade. Thread-safe."""
    global _off_hours_trade_count
    with _off_hours_lock:  # HIGH FIX #7: Lock before modifying shared state
        _off_hours_trade_count += 1


def _register_confirmed_close_events(history_sync: dict) -> None:
    """Feed each newly confirmed economic close to the loss guard once."""
    close_events = (history_sync or {}).get('close_events', []) or []
    for event in sorted(close_events, key=lambda item: str(item.get('timestamp') or '')):
        outcome = str(event.get('result', '') or '').upper()
        if outcome not in {'WIN', 'LOSS'}:
            continue
        register_loss_pause_result(
            trade_result=outcome,
            ticket=event.get('ticket'),
            profit=float(event.get('profit', 0.0) or 0.0),
        )

def maybe_skip_analysis(now, rates, atr, market_regime, session, confidence_pct):
    global _last_analysis_hash, _last_analysis_time
    current_hash = build_market_snapshot_hash(rates, atr, market_regime, session, confidence_pct)
    if current_hash is None:
        return False
    if _last_analysis_hash == current_hash and (now - _last_analysis_time) < 20:
        print('ANALYSIS_SKIPPED | NO_MEANINGFUL_CHANGE')
        return True
    _last_analysis_hash = current_hash
    _last_analysis_time = now
    return False


def _safe_mid_price(tick) -> float:
    if tick is None:
        return 0.0
    try:
        return round((float(tick.ask) + float(tick.bid)) / 2.0, 5)
    except Exception:
        return 0.0


def _get_rate_close(rate) -> float:
    return _get_rate_close_helper(rate)


def _derive_signal(structure_bias: str, liquidity_bias: str) -> str:
    return _derive_signal_helper(structure_bias, liquidity_bias)


def _smc_strength_from_details(details: dict) -> float:
    return _smc_strength_from_details_helper(details)


def _run_resolvers_cycle(snapshot: dict) -> None:
    """
    FER3ON PHASE 0.5 (2026-09-01): Resolver integration.
    Resolve PENDING records in shadow ledgers against real candles.
    Runs every heartbeat to populate rejected_win_rate and entry_plan outcomes.
    NEVER raises — all exceptions swallowed.
    """
    global _resolver_candles_cache
    try:
        from core.resolver_telemetry import record_cycle
        _telemetry = {
            'resolver_cycles_run': 1,
            'snapshot_ready': bool(snapshot.get('ready')),
            'rates_is_none': snapshot.get('rates') is None,
            'candles_len': 0,
            'skipped_not_ready': False,
            'skipped_short_rates': False,
            'converted_candles': 0,
            'rejected_resolved': 0,
            'entry_plans_resolved': 0,
            'exit_actions_logged': 0,
            'exit_outcomes_resolved': 0,
            'rates_source': 'snapshot',
            'error': None,
        }
        if not snapshot.get('ready') or snapshot.get('rates') is None:
            _telemetry['skipped_not_ready'] = True
            record_cycle(_telemetry)
            return
        
        rates = snapshot.get('rates', [])
        # Resolver history is independent from the short decision window.
        # This lets old PENDING records reach their signal timestamp without
        # changing the data volume used by the live decision path.
        try:
            from core.settings import RESOLVER_HISTORY_BARS
            if mt5 is not None and RESOLVER_HISTORY_BARS > len(rates):
                historical_rates = mt5.copy_rates_from_pos(
                    SYMBOL, mt5.TIMEFRAME_M5, 0, int(RESOLVER_HISTORY_BARS)
                )
                if historical_rates is not None and len(historical_rates) > len(rates):
                    rates = historical_rates
                    _telemetry['rates_source'] = 'historical_mt5'
        except Exception as exc:
            _telemetry['error'] = f'HISTORY_FETCH:{type(exc).__name__}'
        if len(rates) < 30:
            _telemetry['skipped_short_rates'] = True
            _telemetry['candles_len'] = len(rates)
            record_cycle(_telemetry)
            return
        
        # Convert MT5 rates to resolver format
        candles = _rates_to_candles_helper(rates)
        _resolver_candles_cache = candles
        
        if len(candles) < 10:
            _telemetry['candles_len'] = len(candles)
            _telemetry['skipped_short_rates'] = True
            record_cycle(_telemetry)
            return
        _telemetry['candles_len'] = len(candles)
        _telemetry['converted_candles'] = len(candles)
        
        # Resolve REJECTED_SHADOW outcomes
        try:
            from analytics.shadow_counterfactual import resolve_outcomes, summary
            _resolve_res = resolve_outcomes(candles)
            _telemetry['rejected_resolved'] = int(_resolve_res.get('resolved', 0) or 0)
            if _resolve_res.get('resolved', 0) > 0:
                _summary = summary()
                if _summary.get('ready'):
                    wr = _summary.get('win_rate_rejected')
                    print(f'[RESOLVER] REJECTED_SHADOW | resolved={_resolve_res.get("resolved")} | '
                          f'win_rate={wr:.1%} (n={_summary.get("total")}) | {"READY" if wr else "pending"}')
        except Exception as e:
            print(f'⚠️ RESOLVER_REJECTED_SHADOW_FAILED: {e}')
        
        # Resolve ENTRY_PLANS outcomes (when Phase 2 enabled)
        try:
            from core.entry_controller import resolve_entry_plans, get_entry_plans_summary
            _ep_resolve = resolve_entry_plans(candles)
            _telemetry['entry_plans_resolved'] = int(_ep_resolve.get('resolved', 0) or 0)
            if _ep_resolve.get('resolved', 0) > 0:
                _ep_summary = get_entry_plans_summary()
                if _ep_summary.get('ready'):
                    print(f'[RESOLVER] ENTRY_PLANS | resolved={_ep_resolve.get("resolved")} | '
                          f'completion={_ep_summary.get("completion_rate", 0):.1%}')
        except Exception as e:
            print(f'⚠️ RESOLVER_ENTRY_PLANS_FAILED: {e}')

        # Resolve/evaluate Phase 3 exit actions for currently open positions.
        # This is advisory only; no order is sent by core.exit_manager.
        try:
            from core.exit_manager import (
                evaluate_exit,
                log_exit_action,
                resolve_exit_outcomes,
            )
            _exit_outcomes = resolve_exit_outcomes(candles)
            _telemetry['exit_outcomes_resolved'] = int(
                _exit_outcomes.get('resolved', 0) or 0
            )
            positions = mt5.positions_get(symbol=SYMBOL) if mt5 is not None else None
            if positions is not None:
                current_tickets = set()
                for position in positions:
                    ticket = int(getattr(position, 'ticket', 0) or 0)
                    if ticket <= 0:
                        continue
                    current_tickets.add(ticket)
                    pos_type = getattr(position, 'type', None)
                    direction = (
                        'BUY' if pos_type == getattr(mt5, 'POSITION_TYPE_BUY', 0)
                        else 'SELL'
                    )
                    open_time = getattr(position, 'time', None)
                    try:
                        open_time = datetime.fromtimestamp(
                            float(open_time), tz=timezone.utc
                        ).isoformat()
                    except (TypeError, ValueError, OSError, OverflowError):
                        open_time = str(open_time or '')
                    result = evaluate_exit(
                        {
                            'ticket': ticket,
                            'direction': direction,
                            'entry_price': float(getattr(position, 'price_open', 0) or 0),
                            'sl_dist': abs(
                                float(getattr(position, 'price_open', 0) or 0)
                                - float(getattr(position, 'sl', 0) or 0)
                            ),
                            'open_time': open_time,
                            'strategy': strategy_from_magic(
                                getattr(position, 'magic', None),
                                default='SMC',
                            ),
                        },
                        candles,
                        atr=float(snapshot.get('atr', 0) or 0),
                    )
                    action = str(result.get('action', 'NONE'))
                    if action in {'NONE', 'INVALID', 'ERROR'}:
                        continue
                    dedupe_key = (ticket, action, str(result.get('tier', '')))
                    if dedupe_key not in _logged_exit_actions:
                        log_exit_action({
                            'ticket': ticket,
                            'symbol': SYMBOL,
                            'strategy': strategy_from_magic(
                                getattr(position, 'magic', None),
                                default='SMC',
                            ),
                            **result,
                        })
                        _logged_exit_actions.add(dedupe_key)
                        _telemetry['exit_actions_logged'] += 1
                _logged_exit_actions.intersection_update(
                    {key for key in _logged_exit_actions if key[0] in current_tickets}
                )
        except Exception as e:
            _telemetry['error'] = f'EXIT_MANAGER:{type(e).__name__}'
            print(f'⚠️ RESOLVER_EXIT_MANAGER_FAILED: {e}')
        record_cycle(_telemetry)
    except Exception:
        try:
            from core.resolver_telemetry import record_cycle
            record_cycle({
                'resolver_cycles_run': 1,
                'error': 'RESOLVER_OUTER_EXCEPTION',
            })
        except Exception:
            pass


def _account_balance() -> float:
    try:
        account = mt5.account_info() if mt5 is not None else None
        bal = float(getattr(account, 'balance', 0) or 0)
        # FIXED: إذا الحساب جديد أو balance=0 → استخدم BASE_ACCOUNT_BALANCE (1000$)
        if bal <= 0:
            bal = float(BASE_ACCOUNT_BALANCE)
        return bal
    except Exception:
        return float(BASE_ACCOUNT_BALANCE)


def _live_account_balance() -> float | None:
    """Return the broker balance, or None when MT5 cannot provide it."""
    try:
        if mt5 is None:
            return None
        account = mt5.account_info()
        balance = float(getattr(account, 'balance', 0) or 0)
        return balance if balance > 0 else None
    except Exception:
        return None


def _position_counts() -> tuple[int, int] | None:
    """
    Get current and total position counts for the symbol.
    FER3ON FINAL [SAFETY-2]: If MT5 position query fails, return None
    rather than silently returning (0, 0). Silent fallback could allow trades
    when position count is actually unknown, violating MAX_OPEN_TRADES cap.
    Caller must check for None and handle fail-closed (reject trade).
    """
    try:
        if mt5 is None:
            return None
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions is None:
            print(f'🛑 POSITION_COUNT_UNAVAILABLE | MT5 returned None')
            return None
        positions = positions or []
        return len(positions), len(positions)
    except Exception as e:
        print(f'🛑 POSITION_COUNT_UNAVAILABLE | {e}')
        return None


def _get_symbol_point() -> float:
    try:
        if mt5 is not None:
            info = mt5.symbol_info(SYMBOL)
            if info:
                return float(getattr(info, 'point', 0.01) or 0.01)
    except Exception:
        pass
    return 0.01


def _get_broker_min_stop() -> float:
    try:
        if MT5_AVAILABLE and mt5 is not None:
            info = mt5.symbol_info(SYMBOL)
            if info:
                broker_min = int(getattr(info, 'trade_stops_level', 0) or 0)
                point = _get_symbol_point()
                return broker_min * point
    except Exception:
        pass
    return 0


def _build_order_request(
    signal: str,
    lot: float,
    sl_dist: float,
    tp_dist: float,
    atr: float = None,
    strategy: str = 'SMC',
    tick=None,
):
    if tick is None:
        tick = mt5.symbol_info_tick(SYMBOL) if mt5 is not None else None
    symbol_info = mt5.symbol_info(SYMBOL) if mt5 is not None else None
    point = _get_symbol_point()

    # =================================================================
    # [SLTP-4]: single, authoritative SL/TP finalization — see
    # core/sl_tp_finalizer.py. Replaces the previous separate
    # enforce-min-stop + redundant broker_min re-check (already covered
    # internally by _enforce_min_stop_distance) + TP rescale + ATR-cap
    # sequence, which is exactly what let execute_trade silently disagree
    # with what this function built (see [SLTP-3] history).
    # =================================================================
    from core.sl_tp_finalizer import finalize_sl_tp

    original_sl = sl_dist
    original_tp = float(tp_dist)
    final = finalize_sl_tp(
        symbol=SYMBOL,
        sl_dist_raw=sl_dist,
        tp_dist_raw=tp_dist,
        point=point,
        strategy=strategy,
        atr=atr,
    )
    sl_dist = final['sl_dist']
    tp_dist = final['tp_dist']

    if sl_dist != original_sl:
        print(f'🛡 SL_DIST_FIXED | was={original_sl} → now={sl_dist}')
    if tp_dist != original_tp:
        print(f'🛡 TP_ADJUSTED | was={original_tp:.2f} → now={tp_dist:.2f} | rr={final["rr"]}')
    if final['tp_was_atr_capped']:
        try:
            from analytics.tp_cap_monitor import record_tp_cap_event
            record_tp_cap_event(
                strategy=str(strategy or 'SMC').upper(), signal=signal, atr=atr,
                sl_dist=sl_dist, tp_dist_requested=original_tp,
                tp_dist_capped=tp_dist,
                cap_multiplier_atr=float(get_tp_cap_multiplier(strategy)),
                cap_multiplier_sl=float(get_tp_sl_multiplier(strategy)),
            )
        except Exception as _tp_log_err:
            print(f'⚠️ TP_CAP_MONITOR_LOG_FAILED (non-fatal): {_tp_log_err}')

    if str(signal).upper() == 'SELL':
        order_type = mt5.ORDER_TYPE_SELL
        price = float(getattr(tick, 'bid', 0.0) or 0.0)
        # FER3ON FINAL BUGFIX [SLTP-1]: sl_dist/tp_dist are RAW PRICE UNITS
        # from the adaptive engine (e.g. $29.35 for gold), not points — used
        # directly here, not multiplied by `point` again. See
        # FER3ON_FINAL_CHANGELOG.md [SLTP-1] and core/trailing_stop.py,
        # which already used this same convention correctly.
        sl = round(price + sl_dist, 5)
        tp = round(price - tp_dist, 5)
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = float(getattr(tick, 'ask', 0.0) or 0.0)
        sl = round(price - sl_dist, 5)
        tp = round(price + tp_dist, 5)

    # =================================================================
    # V3.0.1-SLTP-FIXED: معلومات SL/TP للمراجعة قبل الإرسال
    # =================================================================
    try:
        sl_dist_pts = abs(price - sl)
        tp_dist_pts = abs(price - tp)
        rr = round(tp_dist_pts / sl_dist_pts, 2) if sl_dist_pts > 0 else 0.0
        print(
            f'🛡 SL/TP BUILT | signal={signal} price={price} sl={sl} tp={tp} '
            f'sl_dist={sl_dist_pts:.2f}pts tp_dist={tp_dist_pts:.2f}pts RR={rr}'
        )
    except Exception as _exc:
        print(f'⚠️ SL/TP info log failed: {_exc}')

    # =================================================================
    # FIXED: نوع الـ filling — IOC بدل RETURN
    # =================================================================
    filling = getattr(symbol_info, 'filling_mode', None) if symbol_info else None
    if filling is None or filling not in (0, 1, 2):
        filling = mt5.ORDER_FILLING_IOC

    return {
        'symbol': SYMBOL,
        'action': mt5.TRADE_ACTION_DEAL,
        'volume': float(lot),
        'type': order_type,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': DAILY_MAGIC if str(strategy).upper() == 'DAILY' else SMC_MAGIC,
        'comment': f'F3-{str(strategy).upper()}',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': filling,
    }


def _build_live_snapshot(symbol: str, strategy: str = 'SMC') -> dict:
    strategy = str(strategy or 'SMC').strip().upper()
    if strategy not in {'SMC', 'DAILY'}:
        return {'ready': False, 'reason': 'UNSUPPORTED_STRATEGY', 'strategy': strategy}

    now = datetime.now(timezone.utc)

    # =========================================================================
    # FER3ON FINAL — LONDON OPEN VOLATILE WINDOW (Hard Block)
    # Ported from V3.7 main.py (which documented 33% WR on 36 trades, -$178
    # during 08:00-10:00 UTC London open). Hard block before any other work —
    # blocks every strategy during this window and saves the regime/structure/
    # ATR calculations that would otherwise run for a snapshot that's about
    # to be discarded anyway. See build spec Merge item #2 /
    # FER3ON_FINAL_CHANGELOG.md [MAIN-1].
    # =========================================================================
    if LONDON_VOLATILE_BLOCK_ENABLED and LONDON_VOLATILE_START <= now.hour < LONDON_VOLATILE_END:
        return {
            'ready': False,
            'reason': f'LONDON_VOLATILE_WINDOW_BLOCK ({LONDON_VOLATILE_START:02d}:00-{LONDON_VOLATILE_END:02d}:00 UTC)',
            'tick': mt5.symbol_info_tick(symbol) if mt5 is not None else None,
            'session': get_session(now.hour),
            'phase': detect_session_phase(now.hour, now.minute),
        }

    tick = mt5.symbol_info_tick(symbol) if mt5 is not None else None
    rates = mt5.copy_rates_from_pos(
        symbol,
        mt5.TIMEFRAME_M5,
        1 if strategy == 'SMC' else 0,
        120,
    ) if mt5 is not None else None
    if rates is None or len(rates) < 30:
        return {
            'ready': False,
            'reason': 'NO_MARKET_RATES',
            'tick': tick,
            'session': get_session(now.hour),
            'phase': detect_session_phase(now.hour, now.minute),
        }

    session_name = get_session(now.hour)
    phase = detect_session_phase(now.hour, now.minute)
    regime = detect_market_regime(symbol)
    atr = float(calculate_atr(rates) or 0.0)
    structure = get_market_structure(symbol)
    liquidity = get_liquidity_bias(symbol)
    current_price = _get_rate_close(rates[-1])
    structure_analysis = analyze_swing_structure(rates, current_price=current_price)
    structure_rates = rates
    strategy_atr = atr
    if strategy == 'DAILY':
        h4_rates = (
            mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 120)
            if mt5 is not None else None
        )
        if h4_rates is None or len(h4_rates) < 31:
            return {
                'ready': False,
                'reason': 'DAILY_H4_STRUCTURE_UNAVAILABLE',
                'strategy': strategy,
                'tick': tick,
                'rates': rates,
                'session': session_name,
            }
        closed_h4_rates = h4_rates[:-1]
        structure_rates = closed_h4_rates
        strategy_atr = float(calculate_atr(closed_h4_rates) or 0.0)
        if strategy_atr <= 0:
            return {
                'ready': False,
                'reason': 'DAILY_H4_ATR_UNAVAILABLE',
                'strategy': strategy,
                'tick': tick,
                'rates': rates,
                'session': session_name,
            }
        structure_analysis = analyze_swing_structure(
            closed_h4_rates,
            current_price=current_price,
        )
    daily_bias = 'NEUTRAL'
    if strategy == 'DAILY':
        try:
            from core.daily.signal import get_daily_setup
            signal, daily_bias = get_daily_setup(symbol)
        except Exception as exc:
            return {
                'ready': False,
                'reason': f'DAILY_SIGNAL_ERROR:{type(exc).__name__}',
                'strategy': strategy,
                'tick': tick,
            }
    else:
        signal = _derive_signal(
            structure_analysis.get('structure_bias', structure.get('bias', 'NEUTRAL')),
            liquidity.get('bias'),
        )
        if signal == 'NONE':
            signal = _derive_signal(structure.get('bias'), liquidity.get('bias'))
    if signal == 'NONE':
        return {
            'ready': False,
            'reason': 'DAILY_SIGNAL_UNAVAILABLE' if strategy == 'DAILY' else 'NO_DIRECTIONAL_SIGNAL',
            'strategy': strategy,
            'tick': tick,
            'rates': rates,
            'atr': atr,
            'market_regime': regime,
            'session': session_name,
            'phase': phase,
        }

    try:
        live_entry_price = (
            float(tick.ask if signal == 'BUY' else tick.bid)
            if tick is not None else 0.0
        )
    except (AttributeError, TypeError, ValueError):
        live_entry_price = 0.0
    if live_entry_price <= 0:
        return {
            'ready': False,
            'reason': 'ENTRY_PRICE_UNAVAILABLE',
            'tick': tick,
            'signal': signal,
            'structure_analysis': structure_analysis,
        }

    entry_readiness = (
        evaluate_entry_readiness(structure_analysis, entry_price=current_price)
        if strategy == 'SMC'
        else {'ready': True, 'reason': 'DAILY_D1_H4_CLOSED_BAR_CONFIRMATION'}
    )
    if not entry_readiness.get('ready', False):
        return {
            'ready': False,
            'reason': 'STRUCTURE_NOT_READY',
            'tick': tick,
            'rates': rates,
            'atr': atr,
            'market_regime': regime,
            'session': session_name,
            'phase': phase,
            'signal': signal,
            'structure': structure,
            'structure_analysis': structure_analysis,
            'entry_readiness': entry_readiness,
        }

    candle = check_candle_trigger(symbol, signal, strategy, rates=rates)
    if strategy == 'SMC':
        smc_confirmed, entry_grade, smc_details = check_smc_entry_sequence(symbol, signal)
        if not smc_confirmed:
            return {
                'ready': False,
                'reason': 'SMC_ENTRY_NOT_CONFIRMED',
                'strategy': strategy,
                'signal': signal,
                'tick': tick,
                'rates': rates,
                'atr': atr,
                'market_regime': regime,
                'session': session_name,
                'phase': phase,
                'structure': structure,
                'structure_analysis': structure_analysis,
                'smc_details': smc_details,
                'entry_grade': entry_grade,
            }
    else:
        smc_confirmed = True
        entry_grade = 'DAILY_D1_H4_CONFIRMED'
        smc_details = {'grade_score': 75.0, 'conditions_met': 3}
    smc_strength = _smc_strength_from_details(smc_details)
    session_history = get_session_confidence(now.hour)
    session_score = compute_session_intelligence_score(phase, session_history, signal)
    if strategy == 'SMC':
        daily_bias = structure.get('bias', 'NEUTRAL')
    mtf_direction = daily_bias if daily_bias in {'BUY', 'SELL'} else signal
    mtf_strength = 3 if structure.get('mtf_aligned') else 2 if daily_bias in {'BUY', 'SELL'} else 0

    news_state = is_news_active(symbol)
    if news_state['is_news'] and news_state['impact'] == 'HIGH':
        print(
            f"📰 NEWS_HIGH | event={news_state['event']} "
            f"Δ={news_state['minutes_to_event']:.0f}m → cycle paused"
        )
        return {
            'ready': False,
            'reason': 'NEWS_HIGH_IMPACT',
            'tick': tick,
            'session': session_name,
            'phase': phase,
            'news_state': news_state,
        }

    confidence = get_confidence_v2(
        strategy=strategy,
        signal=signal,
        market_regime=regime,
        mtf_direction=mtf_direction,
        mtf_strength=mtf_strength,
        smc_strength=smc_strength,
        entry_grade=entry_grade,
        session_name=session_name,
        session_score=session_score,
        liquidity_bias=liquidity.get('bias', 'NEUTRAL'),
        is_news=news_state['is_news'],
        news_impact=news_state['impact'],
        asian_data=liquidity,
    )

    quality_score = round(max(float(smc_details.get('grade_score', 0) or 0), float(candle.get('score', 0) or 0), 50.0), 2)

    # === Real sweep probability (was binary 0/100) ===
    # نستخدم core/sweep_predictor.py الحقيقي بدل التقدير الثنائي القديم.
    # لو الحساب فشل لأي سبب نسقط بأمان على المنطق القديم كـ fallback.
    try:
        from core.sweep_predictor import compute_sweep_probability as _compute_sweep_prob
        _current_price = float(tick.ask if signal == 'BUY' else tick.bid) if tick else 0.0
        _sweep_res = _compute_sweep_prob(
            signal=signal,
            equal_highs=liquidity.get('equal_highs') or [],
            equal_lows=liquidity.get('equal_lows') or [],
            liquidity_pools=liquidity.get('pools') or [],
            current_price=_current_price,
            session=session_name,
            distance_to_pool=liquidity.get('distance_next_pool'),
        )
        sweep_probability = float(_sweep_res.get('sweep_probability', 0.0) or 0.0)
        # لو المُتنبّئ معطّل أو النتيجة صفر لكن هناك سويب مؤكد فعليًا، نعوّض بمنطق قديم.
        if sweep_probability <= 0.0 and liquidity.get('sweep') not in {None, '', 'NONE'}:
            sweep_probability = 100.0
    except Exception as _sweep_err:
        # سقوط آمن على المنطق القديم
        sweep_probability = 100.0 if liquidity.get('sweep') not in {None, '', 'NONE'} else 0.0

    quality_gate = evaluate_quality_gate(
        quality_score=quality_score,
        confidence_pct=confidence.get('pct', 0),
        strategy=strategy,
        session=session_name,
        smc_entry_confirmed=bool(smc_confirmed),
        candle_trigger_confirmed=bool(candle.get('confirmed')),
        sweep_probability=sweep_probability,
        missed_opportunity_score=0,
        ml_score=50,
    )

    brain = get_master_score(strategy, regime, session_name)

    broker_min = _get_broker_min_stop()
    execution = {
        'grade': 'B',
        'spread_pts': 0.0,
        'rr_ratio': 1.5,
        'score': 50.0,
    }
    structure_strength = max(
        float(structure.get('confidence', 0.5) or 0.5),
        float(structure_analysis.get('structure_strength', 0.0) or 0.0) / 100.0,
    )
    adaptive = calculate_adaptive_sl_tp(
        atr=strategy_atr,
        strategy=strategy,
        lot=lot if 'lot' in locals() else 0.01,
        confidence=confidence.get('pct', 0) / 100.0,
        quality_score=quality_score,
        market_regime=regime,
        session=session_name,
        structure_strength=structure_strength,
        liquidity=liquidity.get('score', 0) / 100.0,
        volatility=0.5,
        spread=execution.get('spread_pts', 0),
        execution_grade=execution.get('grade', 'B'),
        broker_stop_level=broker_min,
        broker_stop_fallback=0.0,
        min_sl=get_min_sl_dollars(),  # [REARCH-1]: single source of truth, see core/settings.py
        entry_price=live_entry_price,
        signal=signal,
        structure_analysis=structure_analysis,
    )
    if not adaptive.get('stop_valid', False):
        print(
            f"🛑 STRUCTURAL_STOP_REJECTED | reason={adaptive.get('stop_reason')}"
            f" source={adaptive.get('selected_stop_source')}"
            f" candidate={adaptive.get('sl_distance')}"
        )
        return {
            'ready': False,
            'reason': adaptive.get('stop_reason') or 'INVALID_STOP_DISTANCE',
            'tick': tick,
            'signal': signal,
            'atr': atr,
            'market_regime': regime,
            'session': session_name,
            'structure_analysis': structure_analysis,
            'adaptive_sltp': adaptive,
        }
    sl_dist = adaptive['sl_distance']
    tp_dist = adaptive['tp_distance']

    execution = execute_intelligence_check(
        symbol=symbol,
        signal=signal,
        sl_dist=sl_dist,
        tp_dist=tp_dist,
        atr=strategy_atr,
        liquidity_map={
            'liquidity_score': liquidity.get('score', 0),
            'direction': 'UP' if liquidity.get('bias') == 'BUY' else 'DOWN' if liquidity.get('bias') == 'SELL' else 'NEUTRAL',
            'distance_next': max(tp_dist * 3, 1.0),
        },
        session=session_name,
        quality_score=quality_score,
        strategy=strategy,
        market_regime=regime,
    )

    features_array, feature_record = extract_live_features(
        symbol=symbol,
        strategy=strategy,
        signal=signal,
        market_regime=regime,
        session=session_name,
        quality_score=quality_score,
        confidence_pct=confidence.get('pct', 0),
        choch_state=structure.get('structure', 'UNKNOWN'),
        liq_map_score=liquidity.get('score', 0),
        exec_grade=execution.get('grade', 'REJECT'),
        rr_ratio=execution.get('rr_ratio', 0),
        spread_pts=execution.get('spread_pts', 0),
        mtf_strength=mtf_strength,
        mtf_structural=1 if structure.get('mtf_aligned') else 0,
        atr=strategy_atr,
        key_levels={
            'PDH': liquidity.get('asian_high', 0),
            'PDL': liquidity.get('asian_low', 0),
        },
    )

    ml_result = ml_evaluate_trade(
        features_array=features_array,
        state_key=f'{signal}|{regime}|{session_name}|{entry_grade}',
        signal=signal,
        quality_score=quality_score,
        exec_grade=execution.get('grade', 'REJECT'),
        market_regime=regime,
        session=session_name,
        mtf_strength=mtf_strength,
        choch_active=structure.get('structure', 'UNKNOWN').startswith('TRANSITION'),
        liq_score=liquidity.get('score', 0),
    )

    quality_gate = evaluate_quality_gate(
        quality_score=quality_score,
        confidence_pct=confidence.get('pct', 0),
        strategy=strategy,
        session=session_name,
        smc_entry_confirmed=bool(smc_confirmed),
        candle_trigger_confirmed=bool(candle.get('confirmed')),
        sweep_probability=sweep_probability,
        missed_opportunity_score=0,
        ml_score=ml_result.get('ml_score', 50),
    )

    structural_targets = select_structural_targets(
        structure_analysis,
        entry_price=live_entry_price,
        signal=signal,
    )
    swing_report = build_swing_structure_report(
        structure_analysis,
        entry_price=live_entry_price,
        signal=signal,
        stop_distance=sl_dist,
        tp_distance=tp_dist,
        final_rr=adaptive.get('risk_reward', 0.0),
        stop_source=adaptive.get('selected_stop_source'),
        stop_anchor=adaptive.get('selected_stop_anchor'),
        stop_reason=adaptive.get('stop_selection_reason'),
        stop_buffer=adaptive.get('structure_buffer'),
        target_source=adaptive.get('target_source'),
        target_price=adaptive.get('target_price'),
    )
    print(swing_report)

    position_result = _position_counts()
    if position_result is None:
        # MT5 position query failed — fail-closed: skip this snapshot
        return {
            'ready': False,
            'reason': 'POSITION_COUNT_UNAVAILABLE',
            'tick': tick,
        }
    current_positions, total_positions = position_result
    live_balance = _live_account_balance()
    if live_balance is None:
        return {
            'ready': False,
            'reason': 'ACCOUNT_BALANCE_UNAVAILABLE',
            'tick': tick,
        }
    position_limits = evaluate_position_limits(strategy=strategy, current_positions=current_positions, total_positions=total_positions)
    balance = live_balance
    loss_limits = get_loss_limits_status(balance=balance)
    risk_limits_hit = not position_limits.get('allowed', True) or loss_limits.get('daily_used', 0) >= loss_limits.get('daily_limit', 0) or loss_limits.get('weekly_used', 0) >= loss_limits.get('weekly_limit', 0)

    ctx = build_decision_context(
        strategy=strategy,
        signal=signal,
        symbol=symbol,
        quality_score=quality_score,
        confidence_pct=confidence.get('pct', 0),
        brain_score=brain.get('master_score', 50),
        execution_score=execution.get('score', 0),
        execution_grade=execution.get('grade', 'UNKNOWN'),
        structure_quality=float(structure_analysis.get('structure_strength', 50.0) or 50.0),
        daily_bias=daily_bias if daily_bias in {'BUY', 'SELL'} else 'NONE',
        mtf_strength=mtf_strength,
        smc_strength=smc_strength,
        smc_entry_confirmed=bool(smc_confirmed),
        candle_trigger_confirmed=bool(candle.get('confirmed')),
        candle_weight=int(candle.get('weight', 0) or 0),
        candle_bonus=float(candle.get('candle_bonus', 0) or 0),
        candle_penalty=float(candle.get('candle_penalty', 0) or 0),
        liquidity_alignment=round(float(liquidity.get('score', 0) or 0) / 15.0 * 100.0, 2),
        sweep_probability=sweep_probability,
        session=session_name,
        market_regime=regime,
        session_score=session_score,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=_cooldown_active_for(strategy),
        market_unsafe=regime == 'CRISIS',
        daily_loss_capped=loss_limits.get('daily_used', 0) >= loss_limits.get('daily_limit', 0),
        emergency_stop=False,
        spread_ratio=execution.get('spread_pct', 0),
        atr_sufficient=strategy_atr >= 1.0,
        rr_ratio=execution.get('rr_ratio', 0),
        ml_score=ml_result.get('ml_score', 50),
        ml_rl_action=ml_result.get('rl_action', 'PASS'),
        memory_score=brain.get('memory_score', brain.get('history_score', 50)),
        dna_score=brain.get('dna_score', 50),
        # §3.2 Institutional Session Engine — reuse the exact same UTC
        # timestamp already used above for session_name/phase, rather than
        # letting build_decision_context() call datetime.now() again a few
        # lines later (functionally equivalent, this is just exact).
        hour=now.hour,
        minute=now.minute,
    )

    last_structure_rate = structure_rates[-1]
    decision_bar_time = getattr(last_structure_rate, 'time', None)
    if decision_bar_time is None:
        try:
            decision_bar_time = last_structure_rate['time']
        except (KeyError, TypeError, IndexError, ValueError):
            decision_bar_time = ''

    return {
        'ready': True,
        'strategy': strategy,
        'tick': tick,
        'rates': rates,
        'decision_bar_time': decision_bar_time,
        'atr': strategy_atr,
        'management_atr': atr,
        'market_regime': regime,
        'session': session_name,
        'phase': phase,
        'signal': signal,
        'structure': structure,
        'structure_analysis': structure_analysis,
        'liquidity': liquidity,
        'mtf_strength': mtf_strength,
        'candle': candle,
        'smc_confirmed': smc_confirmed,
        'entry_grade': entry_grade,
        'smc_details': smc_details,
        'confidence': confidence,
        'quality_gate': quality_gate,
        'quality_score': quality_score,
        'brain': brain,
        'execution': execution,
        'ml': ml_result,
        'feature_record': feature_record,
        'decision_context': ctx,
        'news_state': news_state,
        'position_limits': position_limits,
        'loss_limits': loss_limits,
        'balance': balance,
        'entry_price': live_entry_price,
        'sl_dist': sl_dist,
        'tp_dist': tp_dist,
        'tp_tiers': adaptive.get('tp_tiers'),
        'adaptive_sltp': adaptive,
        'tp_target_price': adaptive.get('target_price'),
        'tp_target_source': adaptive.get('target_source'),
        'entry_readiness': entry_readiness,
        'structural_targets': structural_targets,
        'swing_structure_report': swing_report,
    }


def _select_strategy_snapshot(
    symbol: str,
    snapshot: dict,
    *,
    recommended_strategy: str = 'SMC',
    recommendation_confidence: float = 0.0,
) -> dict:
    """Route a valid Daily candidate only through the explicitly enabled path."""
    if not DAILY_RUNTIME_ENABLED:
        return snapshot

    current_strategy = str(snapshot.get('strategy') or 'SMC').upper()
    try:
        recommendation_confidence = float(recommendation_confidence or 0.0)
    except (TypeError, ValueError):
        recommendation_confidence = 0.0

    should_try_daily = (
        not snapshot.get('ready')
        and snapshot.get('reason') in {'NO_DIRECTIONAL_SIGNAL', 'STRUCTURE_NOT_READY'}
    ) or (
        snapshot.get('ready')
        and current_strategy != 'DAILY'
        and str(recommended_strategy or '').upper() == 'DAILY'
        and recommendation_confidence >= 0.7
    )
    if not should_try_daily:
        return snapshot

    try:
        daily_snapshot = _build_live_snapshot(symbol, strategy='DAILY')
    except Exception as error:
        print(f'⚠️ DAILY_SNAPSHOT_ERROR (non-fatal): {error}')
        return snapshot

    if daily_snapshot.get('ready') is True:
        return daily_snapshot
    if snapshot.get('ready'):
        print(
            "[STRATEGY_ROUTER] DAILY recommendation ignored; "
            f"candidate unavailable: {daily_snapshot.get('reason', 'UNKNOWN')}"
        )
    return snapshot


def main():
    print('=' * 60)
    print('   FER3ON-AI-V3-PLUS-PLUS-PLUS')
    print(f'   حساب الوسيط | {MAX_DAILY_TRADES} صفقة يومياً | Demo/Live Hardened')
    print('=' * 60)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f'MT5 available: {MT5_AVAILABLE}')
    print(f'Shadow-only runtime: {SHADOW_ONLY_RUNTIME} | max cycles: {SHADOW_RUN_MAX_CYCLES or "unlimited"}')

    try:
        if not connect_mt5():
            print('🛑 MT5 connection failed (live trading blocked)')
    except Exception as exc:
        print(f'MT5 connect warning: {exc}')

    from core.demo_execution import demo_execution_status
    _demo_orders_allowed, _demo_orders_reason = demo_execution_status()
    print(
        f'Demo order execution: '
        f'{"ENABLED" if _demo_orders_allowed else "BLOCKED"} ({_demo_orders_reason})'
    )

    startup_balance = _live_account_balance()
    if startup_balance is None:
        print('Account balance: unavailable (live trading blocked)')
    else:
        print(f'Account balance: ${startup_balance:.2f} (MT5)')
        sync_portfolio_equity(startup_balance)
    print(f'Max daily trades: {MAX_DAILY_TRADES}')
    print(f'Testing mode lot caps: {TESTING_MODE_LOT_CAPS}')

    # FIXED: إظهار broker minimum stop distance عند التشغيل
    broker_min = _get_broker_min_stop()
    print(f'Broker XAUUSD min stop distance: {broker_min:.5f} ({broker_min / 0.01:.0f} points)')

    try:
        startup_result = run_startup_check()
        print(f"Startup check: {startup_result.get('startup_status', 'unknown')}")
    except Exception as exc:
        print(f'Startup check skipped: {exc}')
        startup_result = {}

    # FIX: production_ready must reflect genuine system health, not "did a
    # trade get approved this specific heartbeat". Both run_watchdog_cycle()
    # call sites below used to tie production_ready to per-cycle trade
    # approval (one hardcoded to False outright on the loss-pause-guard
    # path) — since most heartbeats correctly reject a trade (that's
    # normal, not a health problem), this made the watchdog report
    # DEGRADED/STARTUP_BLOCK on nearly every single cycle, burying any
    # genuine health signal in constant false-alarm noise.
    _system_startup_ready = startup_result.get('startup_status') == 'SYSTEM_READY'

    # [FER3ON-FIX-2026-08-21] ACCOUNT SCOPE — لازم قبل أي قراءة لـ
    # loss_pause_guard.json أو adaptive_state.json، عشان لو الحساب اتغيّر
    # (ديمو جديد مثلًا) نصفّر العدّادات القديمة قبل ما تأثر على أول دورة.
    try:
        from core.account_scope import ensure_account_scope
        ensure_account_scope()
    except Exception as exc:
        print(f'Account-scope check warning: {exc}')

    try:
        sync_mt5_history()
        update_certification_progress()
    except Exception as exc:
        print(f'History/bootstrap sync warning: {exc}')

    # =========================================================================
    # الإصلاح #1 (حرج): ربط Quant Engine بالصفقات الحقيقية
    # trades.csv يحتوي الصفقات الفعلية — truth_layer كان فارغًا منها.
    # هذا الجسر يُغذّي truth_layer بكل الصفقات المُغلقة من CSV
    # حتى تعمل ميزات V6 (tier, risk_multiplier) بشكل صحيح.
    # =========================================================================
    try:
        sync_csv_to_truth_layer()
    except Exception as exc:
        print(f'⚠️ CSV→TruthLayer sync warning: {exc}')
    try:
        from analytics.truth_layer import persist_daily_report
        from analytics.setup_analyzer import persist_setup_analysis_report
        persist_daily_report()
        setup_report = persist_setup_analysis_report()
        print(
            '[TRADE_ANALYTICS] refreshed from Truth Layer | '
            f"strategies={len(setup_report.get('strategies', {}))}"
        )
    except Exception as exc:
        print(f'⚠️ TRADE_ANALYTICS_REFRESH_FAILED (startup): {exc}')
    try:
        from analytics.shadow_system_report import persist_shadow_system_report
        shadow_report = persist_shadow_system_report()
        print(
            '[SHADOW_SYSTEM_REVIEW] refreshed | '
            f"systems={shadow_report['summary']['system_count']} "
            f"decisions_due={shadow_report['summary']['decision_required_count']}"
        )
    except Exception as exc:
        print(f'⚠️ SHADOW_SYSTEM_REVIEW_FAILED (startup): {exc}')

    print('Entering trading loop. Press Ctrl+C to stop.')
    print('=' * 60)

    counter = 0
    
    # [PHASE1E] Initialize Unified Strategy Bridge (supports all strategies)
    unified_bridge = None
    if _BRIDGE_AVAILABLE:
        try:
            unified_bridge = UnifiedStrategyBridge()
        except Exception as _bridge_init_err:
            print(f"[PHASE1E] Bridge init warning: {_bridge_init_err}")
    
    try:
        while True:
            if SHADOW_RUN_MAX_CYCLES and counter >= SHADOW_RUN_MAX_CYCLES:
                print(f'Runtime cycle limit reached: {counter}. Exiting safely.')
                break
            counter += 1
            loop_start = time.time()
            now = datetime.now(timezone.utc)
            tick = mt5.symbol_info_tick(SYMBOL) if mt5 is not None else None

            try:
                from core.daily_trade_manager import manage_daily_positions
                manage_daily_positions(SYMBOL)
            except Exception as _daily_management_error:
                print(f'⚠️ DAILY_POSITION_MANAGEMENT_ERROR (non-fatal): {_daily_management_error}')

            if tick is None:
                _mt5_status = 'online' if MT5_AVAILABLE else 'offline'
                print(
                    f'Heartbeat {counter} | {now.strftime("%H:%M:%S")} UTC | '
                    f'MT5={_mt5_status} | tick=unavailable'
                )
            else:
                _mt5_status = 'online' if MT5_AVAILABLE else 'offline'
                print(
                    f'Heartbeat {counter} | {now.strftime("%H:%M:%S")} UTC | '
                    f'MT5={_mt5_status} | bid={tick.bid:.2f} ask={tick.ask:.2f}'
                )

            snapshot = _build_live_snapshot(SYMBOL)
            primary_snapshot = snapshot
            snapshot = _select_strategy_snapshot(SYMBOL, snapshot)
            if snapshot is not primary_snapshot:
                print('[STRATEGY_ROUTER] DAILY selected as directional fallback')
            if not snapshot.get('ready'):
                _skip_reason = snapshot.get('reason', 'NO_RUNTIME_SNAPSHOT')
                print(f'V3+++ skipped: {_skip_reason}')
                time.sleep(CHECK_INTERVAL)
                continue

            if _MISSED_OPPORTUNITY_AVAILABLE:
                try:
                    process_missed_opportunities(SYMBOL)
                except Exception as _missed_eval_err:
                    print(f'⚠️ MISSED_OPPORTUNITY_EVAL_ERROR (non-fatal): {_missed_eval_err}')

            if counter % 60 == 0:
                try:
                    from analytics.shadow_system_report import persist_shadow_system_report
                    persist_shadow_system_report()
                except Exception as _shadow_review_refresh_error:
                    print(
                        '⚠️ SHADOW_SYSTEM_REVIEW_REFRESH_FAILED (periodic): '
                        f'{_shadow_review_refresh_error}'
                    )
                try:
                    from analytics.performance_drift import detect_performance_drift
                    from analytics.performance_repository import get_all_trades
                    drift = detect_performance_drift(
                        [vars(trade) if hasattr(trade, '__dict__') else trade for trade in get_all_trades()]
                    )
                    from analytics.shadow_context_collector import record_performance_snapshot
                    record_performance_snapshot(
                        [vars(trade) if hasattr(trade, '__dict__') else trade for trade in get_all_trades()],
                        drift_result=drift,
                    )
                    if drift.get('alert_count'):
                        print(f"⚠️ PERFORMANCE_DRIFT_SHADOW | alerts={drift['alert_count']}")
                except Exception as _drift_err:
                    print(f'⚠️ PERFORMANCE_DRIFT_ERROR (non-fatal): {_drift_err}')

            # Proactive opportunity zones are prepared and logged only. They
            # never replace the live decision or reach the order executor.
            if counter % max(1, int(PROACTIVE_OPPORTUNITY_SCAN_INTERVAL)) == 0:
                try:
                    from core.entry_controller import scan_opportunity_zones, log_entry_plan
                    if PROACTIVE_OPPORTUNITY_SCAN_ENABLED:
                        for _zone in scan_opportunity_zones(
                            symbol=SYMBOL,
                            rates=snapshot.get('rates'),
                            atr=snapshot.get('atr'),
                            structure_analysis=snapshot.get('structure_analysis'),
                            strategy=snapshot.get('strategy') or 'SMC',
                        ):
                            log_entry_plan(_zone)
                except Exception as _zone_err:
                    print(f'⚠️ PROACTIVE_OPPORTUNITY_SCAN_ERROR (non-fatal): {_zone_err}')
            
            # =====================================================================
            # 🌑 SHADOW LEARNING ENGINE — استخراج رؤى من الإشارات المرفوضة
            # =====================================================================
            if _SHADOW_LEARNING_AVAILABLE and counter % 60 == 0:  # كل 60 دورة
                try:
                    shadow_engine = ShadowLearningEngine()
                    shadow_result = shadow_engine.run()
                    if shadow_result.get('status') == 'success':
                        shadow_wr = shadow_result.get('observed_win_rate')
                        if shadow_wr is not None:
                            print(
                                f"🌑 SHADOW_LEARNING | resolved="
                                f"{shadow_result.get('signals_analyzed')} rejected signals "
                                f"| observed_wr={shadow_wr:.2%}"
                            )
                    elif shadow_result.get('status') == 'insufficient_data':
                        print(
                            f"🌑 SHADOW_LEARNING | waiting for resolved candle outcomes "
                            f"(unresolved={shadow_result.get('unresolved_signals', 0)})"
                        )
                except Exception as e:
                    print(f"⚠️ SHADOW_LEARNING_ERROR: {e}")
            
            # =====================================================================
            # 🎯 MULTI-DIMENSIONAL REGIME ANALYZER — تحديد السياق والاستراتيجية
            # =====================================================================
            recommended_strategy = snapshot.get('strategy', 'SMC')
            regime_confidence = 0.5
            regime_params = {}
            
            if _MULTI_REGIME_AVAILABLE:
                try:
                    _regime_rates = snapshot.get('rates')
                    regime_analyzer = MultiDimensionalRegimeAnalyzer(
                        rates_data=_regime_rates if _regime_rates is not None else []
                    )
                    regime_context = regime_analyzer.analyze()
                    recommended_strategy = regime_context.recommended_strategy
                    regime_confidence = regime_context.strategy_confidence
                    regime_params = regime_context.suggested_parameters
                    try:
                        from analytics.shadow_context_collector import record_regime_observation
                        record_regime_observation(
                            symbol=SYMBOL,
                            primary_regime=regime_context.primary_regime,
                            recommended_strategy=recommended_strategy,
                            strategy_confidence=regime_confidence,
                            observed_strategy=snapshot.get('strategy', 'SMC'),
                            session=snapshot.get('session', 'UNKNOWN'),
                        )
                    except Exception as _regime_log_err:
                        print(f'⚠️ REGIME_SHADOW_LOG_ERROR (non-fatal): {_regime_log_err}')

                    print(f"🎯 REGIME | {regime_context.primary_regime} "
                          f"| Strategy: {recommended_strategy} "
                          f"| Confidence: {regime_confidence:.0%} | OBSERVED")
                except Exception as e:
                    print(f"⚠️ MULTI_REGIME_ERROR: {e}")

            prior_strategy = str(snapshot.get('strategy') or 'SMC').upper()
            snapshot = _select_strategy_snapshot(
                SYMBOL,
                snapshot,
                recommended_strategy=recommended_strategy,
                recommendation_confidence=regime_confidence,
            )
            if snapshot.get('strategy') == 'DAILY' and prior_strategy != 'DAILY':
                print('[STRATEGY_ROUTER] DAILY selected by regime recommendation')

            active_strategy = str(snapshot.get('strategy') or 'SMC').upper()

            # [PHASE1E] Convert selected strategy snapshot to SignalSnapshot for tracing/tracking
            # This is non-breaking: both dict and SignalSnapshot exist in parallel
            smc_signal_snapshot = None
            if unified_bridge is not None:
                try:
                    smc_signal_snapshot = unified_bridge.from_dict_snapshot(
                        dict_snapshot=snapshot,
                        strategy=active_strategy
                    )
                    if smc_signal_snapshot:
                        print(f"[PHASE1E] {active_strategy} | Signal ID: {smc_signal_snapshot.signal_id[:16]}... | "
                              f"Confidence: {smc_signal_snapshot.confidence}% | "
                              f"Quality: {smc_signal_snapshot.quality}%")
                except Exception as _bridge_convert_err:
                    print(f"⚠️ [PHASE1E] SMC Snapshot conversion warning (non-fatal): {_bridge_convert_err}")
            
            # FER3ON PHASE 0.5 (2026-09-01): Resolver cycle
            # Resolve PENDING records in shadow ledgers against real candles
            # This populates rejected_win_rate and entry_plan outcomes every cycle
            try:
                _run_resolvers_cycle(snapshot)
            except Exception as e:
                print(f'⚠️ RESOLVERS_CYCLE_FAILED: {e}')

            # V3.6: استدعاء دوري حقيقي للتريلينج المتقدم (break-even Stage1 +
            # ATR staged trailing Stage2) لكل الصفقات المفتوحة، لكل الاستراتيجيات
            # الأربع (كان قبلها معطّلاً فعليًا — غير مُستدعى من حلقة main على
            # الإطلاق، فقط مرة واحدة عند فتح الصفقة بمنطق بدائي مختلف وbug في
            # فلتر الكومنت). هذا الاستدعاء مستقل تمامًا عن قرار الدخول لهذه
            # الدورة — يعمل دائمًا طالما توفر snapshot صالح.
            # Single coordination point for open-position management.
            _position_management = manage_open_positions(
                SYMBOL,
                snapshot.get('management_atr', snapshot.get('atr', 0.0)),
            )
            if not _position_management.get('ok'):
                print(
                    f"⚠️ POSITION_MANAGER_DEGRADED | "
                    f"errors={_position_management.get('errors', [])}"
                )
                time.sleep(CHECK_INTERVAL)
                continue

            # V3.5 PHASE-1 POST-INCIDENT FIX: reconcile the Portfolio Risk
            # Authority's in-memory open_trades against MT5's real position
            # list every single cycle. This is independent of WHY a mismatch
            # could happen (ticket-id drift, a missed close-sync cycle, a
            # restart that lost in-memory state, etc) — it just guarantees
            # open_trades can never stay stuck pointing at a trade that
            # isn't actually open anymore, which would otherwise block every
            # future trade forever with PER_STRATEGY_MAX_OPEN_HIT.
            try:
                if MT5_AVAILABLE and mt5 is not None:
                    _live_positions = mt5.positions_get(symbol=SYMBOL)
                    if _live_positions is None:
                        print('🛑 RECONCILE_BLOCKED | MT5 position state unavailable')
                        time.sleep(CHECK_INTERVAL)
                        continue
                    _reconcile_result = reconcile_with_live_positions(_live_positions)
                    _removed = _reconcile_result.get('removed', 0)
                    _imported = _reconcile_result.get('imported', 0)
                    if _removed:
                        print(f'🔧 RECONCILE | removed {_removed} stale open_trades entr{"y" if _removed == 1 else "ies"} not found on live MT5 positions')
                    if _imported:
                        print(f'🔧 RECONCILE | imported {_imported} live MT5 position{"" if _imported == 1 else "s"} missing from open_trades (e.g. after a restart)')
            except Exception as exc:
                print(f'⚠️ reconcile_with_live_positions failed (non-fatal): {exc}')

            # V3.5 PHASE-1: ASIA session hard filter — documented 22% WR / 86
            # trades. Stays off until proven otherwise on real data.
            _session_now = snapshot.get('session')
            if _session_now == 'ASIA' and not ASIA_TRADING_ENABLED:
                print(f'🛑 ASIA_SESSION_BLOCK | trading disabled for this session')
                time.sleep(CHECK_INTERVAL)
                continue

            if _session_now == 'OFF_HOURS' and _off_hours_cap_hit():
                print(f'🛑 OFF_HOURS_CAP_HIT | max={OFF_HOURS_MAX_TRADES}/day')
                time.sleep(CHECK_INTERVAL)
                continue

            try:
                limits = get_loss_limits_status(balance=_account_balance())
                if limits['daily_used'] >= limits['daily_limit']:
                    print(f"🛑 DAILY_HALT | used={limits['daily_used']:.2f}% / limit={limits['daily_limit']:.2f}%")
                    time.sleep(60)
                    continue
                if limits['weekly_used'] >= limits['weekly_limit']:
                    print(f"🛑 WEEKLY_HALT | used={limits['weekly_used']:.2f}% / limit={limits['weekly_limit']:.2f}%")
                    time.sleep(60)
                    continue
            except Exception as limits_err:
                print(f"🛑 [PHASE2] Loss limits unavailable; blocking entries: {limits_err}")
                limits = {'daily_used': float('inf'), 'daily_limit': 0.0,
                          'weekly_used': float('inf'), 'weekly_limit': 0.0}
                time.sleep(CHECK_INTERVAL)
                continue

            if maybe_skip_analysis(
                time.time(),
                snapshot.get('rates'),
                snapshot.get('atr'),
                snapshot.get('market_regime'),
                snapshot.get('session'),
                snapshot.get('confidence', {}).get('pct', 0),
            ):
                time.sleep(CHECK_INTERVAL)
                continue

            # PHASE 2 is the canonical runtime authority. It normalizes the
            # snapshot and performs the same unified decision before sizing or
            # execution; no second authority call is allowed after execution.
            authority_result = None
            if _PHASE2_AUTHORITY_AVAILABLE:
                try:
                    phase2_authority = get_unified_authority()
                    strategy_phase2_result = phase2_authority.decide_for_strategy(
                        active_strategy, snapshot,
                        risk_limits_hit=snapshot.get('risk_limits_hit', False),
                        cooldown_active=_cooldown_active_for(active_strategy),
                        daily_loss_capped=limits.get('daily_used', 0) >= limits.get('daily_limit', 0),
                        hour=now.hour,
                        minute=now.minute,
                    )
                    if strategy_phase2_result:
                        authority_result = strategy_phase2_result
                        print(f"[PHASE2] {active_strategy} Authority | Decision: {strategy_phase2_result.decision} | Score: {strategy_phase2_result.composite_score:.1f}")
                except Exception as e:
                    print(f"⚠️ [PHASE2] SMC authority warning: {e}")

            if authority_result is None:
                from core.unified_decision import DecisionResult
                authority_result = DecisionResult(
                    decision='HARD_BLOCK', composite_score=0.0,
                    risk_multiplier=0.0, size_mode='NONE',
                    reasons=['HARD_BLOCK:CANONICAL_AUTHORITY_UNAVAILABLE'],
                    penalties={'authority_unavailable': 100.0}, bonuses={},
                    hard_block_reason='CANONICAL_AUTHORITY_UNAVAILABLE',
                )
            runtime_decision = decision_to_runtime_format(authority_result)
            print(format_authority_log(authority_result))
            
            _mode_val = runtime_decision.get('mode', 'NONE')
            _quality_mode = snapshot.get('quality_gate', {}).get('mode', 'N/A')
            from core.trade_event_ledger import (
                build_entry_attribution,
                create_candidate_id,
                create_snapshot_correlation_id,
            )
            _entry_attribution = build_entry_attribution(snapshot, runtime_decision)
            _candidate_decision_id = create_snapshot_correlation_id(
                snapshot,
                symbol=SYMBOL,
                strategy=active_strategy,
            )
            _candidate_id = create_candidate_id(
                symbol=SYMBOL,
                strategy=active_strategy,
                signal=str(snapshot.get('signal') or ''),
                decision_bar_time=snapshot.get('decision_bar_time'),
            )
            print(
                f'V3-FIXED gate: quality={_quality_mode} '
                f'authority={_mode_val}'
            )

            # ═════════════════════════════════════════════════════════════
            # ARCHITECTURE FIX #3: UNIFIED ALLOCATOR EVALUATION
            # Evaluate opportunity ONCE for all strategies (SMC + runners).
            # This prevents runners from trading on weak signals while SMC
            # waits, or vice versa. All strategies see the same ranking.
            # ═════════════════════════════════════════════════════════════
            _central_opp_rank = None
            _central_risk_multiplier = 1.0
            if _PHASE5_ALLOCATOR_AVAILABLE:
                try:
                    from core.opportunity_allocator import rank_opportunity
                    _conf = snapshot.get('confidence')
                    _conf_pct = (_conf.get('pct') if isinstance(_conf, dict) else _conf) or 0
                    _exec_grade = snapshot['execution'].get('grade', 'C')
                    
                    _central_opp_rank = rank_opportunity(
                        quality_score=float(snapshot.get('quality_score', 0) or 0),
                        confidence_pct=float(_conf_pct or 0),
                        market_regime=str(snapshot.get('market_regime', 'UNKNOWN') or 'UNKNOWN'),
                        session=str(snapshot.get('session', 'UNKNOWN') or 'UNKNOWN'),
                        smc_strength=float(snapshot.get('smc_strength', 0) or 0),
                        mtf_strength=int(snapshot.get('mtf_strength', 0) or 0),
                        execution_grade=str(_exec_grade or 'UNKNOWN'),
                        daily_bias_alignment=bool(snapshot.get('daily_bias_aligned', False)),
                        candidate_id=_candidate_id or None,
                        symbol=SYMBOL,
                        strategy=active_strategy,
                        direction=str(snapshot.get('signal') or ''),
                        decision_bar_time=snapshot.get('decision_bar_time'),
                    )
                    if _central_opp_rank and not _central_opp_rank.should_reject:
                        _central_risk_multiplier = _central_opp_rank.risk_adjustment
                        print(f"[PHASE5-CENTRAL] Opportunity | Grade: {_central_opp_rank.grade} | Score: {_central_opp_rank.score:.0f}")
                except Exception as _central_alloc_err:
                    print(f"⚠️ [PHASE5-CENTRAL] Allocator failed (all strategies get baseline): {_central_alloc_err}")
                    _central_opp_rank = None

            # =================================================================
            # FAIE — Phase-2 spec §5: Shadow-Logging Call Site
            # OPTIONAL, LOGGING-ONLY — see docs/FAIE/PHASE_2_SPECIFICATION.md §5.
            # Runs ChiefDecisionOfficer on the SAME DecisionContext already
            # built for decide_trade() above and appends the advisory
            # Decision to data/faie/shadow_log.jsonl. Zero effect on
            # runtime_decision, snapshot, or any core state — never raises
            # (log_faie_shadow_decision swallows every failure internally),
            # and is entirely gated behind FAIE_SHADOW_LOGGING_ENABLED
            # (enabled by default).
            # =================================================================
            if _FAIE_SHADOW_AVAILABLE and _candidate_id:
                try:
                    _faie_logged = _log_faie_shadow_decision(
                        snapshot['decision_context'],
                        candidate_id=_candidate_id or None,
                        real_decision_summary={
                            'decision': getattr(authority_result, 'decision', None),
                            'composite_score': getattr(authority_result, 'composite_score', None),
                            'risk_multiplier': getattr(authority_result, 'risk_multiplier', None),
                            'size_mode': getattr(authority_result, 'size_mode', None),
                        },
                    )
                    if not _faie_logged:
                        print("[FAIE] Shadow decision was not persisted (non-fatal)")
                except Exception as _faie_shadow_err:
                    # Defense in depth: log_faie_shadow_decision already
                    # catches everything internally and returns False on
                    # failure rather than raising, but this call site stays
                    # wrapped too so a future change to that contract can
                    # never take down the real decision loop.
                    print(f"[FAIE] Shadow logging cycle error (non-fatal): {_faie_shadow_err}")

            # =================================================================
            # FER3ON PHASE 1 — REJECTED_SHADOW counterfactual sidecar.
            # LOGGING ONLY: logs rejected signals for later outcome resolution.
            # Never reads back into the decision; module itself swallows all
            # errors, and this guard is a second belt.
            # =================================================================
            try:
                # Phase 2 — Entry Controller advisory plan (log-only until
                # PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED is switched on for Demo).
                try:
                    from core.entry_controller import plan_entry, log_entry_plan
                    _ep_sig = str(snapshot.get('signal', 'NONE') or 'NONE').upper()
                    if _ep_sig in ('BUY', 'SELL') and _candidate_id:
                        _ep = plan_entry(
                            signal_id=_candidate_id or None,
                            candidate_id=_candidate_id or None,
                            decision_bar_time=snapshot.get('decision_bar_time'),
                            symbol=SYMBOL,
                            direction=_ep_sig,
                            signal_price=float(snapshot.get('entry_price', 0) or 0),
                            atr=float(snapshot.get('atr', 0) or 0),
                            baseline_sl_dist=float(snapshot.get('sl_dist', 0) or 0),
                            baseline_tp_dist=float(snapshot.get('tp_dist', 0) or 0),
                            structure_analysis=snapshot.get('structure_analysis'),
                            strategy=snapshot.get('strategy') or 'SMC',
                        )
                        log_entry_plan(_ep)
                except Exception:
                    pass

                # FER3ON AUDIT FIX 2026-09-01: Log ONLY true rejections, not sizing tiers.
                # Previous bug: recorded EXECUTE_FULL/EXECUTE_REDUCED as "rejected".
                # Now: log only when verdict == REJECT, and capture which gate rejected.
                from analytics.shadow_counterfactual import log_rejected_shadow
                _cf_verdict = str(runtime_decision.get('verdict', ''))
                _cf_mode = str(_mode_val or '').upper()
                
                # Log rejected signal (true rejection, not sizing tier reduction)
                if _cf_verdict == 'REJECT' or 'HARD_BLOCK' in str(runtime_decision.get('hard_block_reason', '')):
                    _cf_conf = snapshot.get('confidence')
                    _cf_gate = snapshot.get('quality_gate')
                    _cf_ctx = snapshot.get('decision_context')
                    _cf_quality_mode = _cf_gate.get('mode', 'UNKNOWN') if isinstance(_cf_gate, dict) else 'UNKNOWN'
                    
                    # Determine which gate stage rejected the signal
                    _cf_gate_stage = 'UNKNOWN'
                    if _cf_quality_mode == 'REJECT':
                        _cf_gate_stage = 'quality_gate'
                    elif not runtime_decision.get('approved', True):
                        _cf_gate_stage = 'authority'  # Portfolio risk authority
                    elif snapshot.get('reason') == 'NEWS_HIGH_IMPACT':
                        _cf_gate_stage = 'news_filter'
                    elif 'BLOCK' in str(runtime_decision.get('reason', '')):
                        _cf_gate_stage = 'hard_block'
                    
                    # Capture the ACTUAL rejection reason
                    _cf_rejection_reason = (
                        runtime_decision.get('hard_block_reason')
                        or runtime_decision.get('reason')
                        or _cf_quality_mode
                        or 'UNKNOWN'
                    )
                    
                    _shadow_signal_id = _candidate_id
                    if not _shadow_signal_id:
                        print(
                            '[SHADOW] Rejected signal not logged: closed decision-bar '
                            'timestamp is unavailable'
                        )
                        _shadow_logged = False
                    else:
                        _shadow_logged = log_rejected_shadow({
                            'signal_id': _shadow_signal_id,
                            'candidate_id': _candidate_id,
                            'decision_id': _candidate_decision_id or None,
                            'symbol': SYMBOL,
                            'direction': snapshot.get('signal', 'NONE'),
                            'signal_time': datetime.now(timezone.utc).isoformat(),
                            'decision_bar_time': snapshot.get('decision_bar_time'),
                            'entry_price': float(snapshot.get('entry_price', 0) or 0),
                            'sl_dist': float(snapshot.get('sl_dist', 0) or 0),
                            'tp_dist': float(snapshot.get('tp_dist', 0) or 0),
                            'atr': float(snapshot.get('atr', 0) or 0),
                            'regime': snapshot.get('market_regime', 'UNKNOWN'),
                            'session': snapshot.get('session', 'UNKNOWN'),
                            'strategy': getattr(_cf_ctx, 'strategy', None) or snapshot.get('strategy') or 'SMC',
                            'confidence': _cf_conf.get('pct') if isinstance(_cf_conf, dict) else _cf_conf,
                            'quality_score': snapshot.get('quality_score', 0),
                            'reject_reason': _cf_rejection_reason,
                            'gate_stage': _cf_gate_stage,
                            'quality_gate_mode': _cf_quality_mode,
                            'verdict': _cf_verdict,
                            'entry_reason': _entry_attribution['entry_reason'],
                            'entry_conditions': _entry_attribution['entry_conditions'],
                            'entry_evidence': _entry_attribution['entry_evidence'],
                            'sltp_mode': 'ATR_PROFILE',
                            'config_revision': 'recovery_atr_v1',
                            'tp1_rr': float(MULTI_TP_PROFILE.get(
                                str(getattr(_cf_ctx, 'strategy', None) or snapshot.get('strategy') or 'SMC').upper(),
                                MULTI_TP_PROFILE.get('SMC', {}),
                            ).get('tp1_rr', 0.0) or 0.0),
                            'tp1_pct': float(MULTI_TP_PROFILE.get(
                                str(getattr(_cf_ctx, 'strategy', None) or snapshot.get('strategy') or 'SMC').upper(),
                                MULTI_TP_PROFILE.get('SMC', {}),
                            ).get('tp1_pct', 0.0) or 0.0),
                            'breakeven_buffer_atr': float(BREAKEVEN_BUFFER_ATR),
                            'risk_per_trade_percent': float(RISK_PER_TRADE_PERCENT),
                            'max_lot': float(MAX_LOT),
                        })
                    if not _shadow_logged:
                        print(
                            '[REJECTED_SHADOW] record was not persisted '
                            f'for signal={_shadow_signal_id}'
                        )
            except Exception as _rejected_shadow_error:
                print(f'⚠️ REJECTED_SHADOW_LOG_FAILED: {_rejected_shadow_error}')

            # =================================================================
            # FER3ON PHASE 4+5 — DECISION LEDGER + OPPORTUNITY ALLOCATOR.
            # ADVISORY/LOGGING ONLY sidecar. Both modules swallow every error
            # internally (same contract as shadow_counterfactual); these two
            # try/except guards are the second belt. LIVE flags default False
            # in settings: nothing here can touch the real decision path.
            # =================================================================
            try:
                from core.decision_ledger import log_decision as _dl_log
                _dl_conf = snapshot.get('confidence')
                _dl_log({
                    'signal_id': f"hb-{datetime.now(timezone.utc).isoformat()}",
                    'symbol': SYMBOL,
                    'direction': snapshot.get('signal', 'NONE'),
                    'strategy': snapshot.get('strategy') or 'SMC',
                    'regime': snapshot.get('market_regime', 'UNKNOWN'),
                    'session': snapshot.get('session', 'UNKNOWN'),
                    'stage': 'AUTHORITY',
                    'decision': str(_mode_val or 'UNKNOWN'),
                    'reason': str(_mode_val or 'UNKNOWN'),
                    'confidence': _dl_conf.get('pct') if isinstance(_dl_conf, dict) else _dl_conf,
                    'quality_score': snapshot.get('quality_score', 0),
                    'entry_reason': _entry_attribution['entry_reason'],
                    'entry_conditions': _entry_attribution['entry_conditions'],
                    'entry_evidence': _entry_attribution['entry_evidence'],
                    'mode': 'LIVE',
                })
            except Exception:
                pass
            try:
                from core.opportunity_allocator import evaluate_opportunity as _oa_eval
                _oa_conf = snapshot.get('confidence')
                _oa_conf_pct = (_oa_conf.get('pct') if isinstance(_oa_conf, dict) else _oa_conf) or 0
                
                # حساب المقاييس الحقيقية من البيانات بدل القيم الوهمية
                _exec_quality = calculate_execution_quality_score()
                _regime_fit = calculate_regime_fit_score(
                    snapshot.get('strategy') or 'SMC',
                    snapshot.get('market_regime', 'UNKNOWN')
                )
                
                _oa_eval({
                    'signal_id': f"hb-{datetime.now(timezone.utc).isoformat()}",
                    'strategy': snapshot.get('strategy') or 'SMC',
                    'session': snapshot.get('session', 'UNKNOWN'),
                    'regime': snapshot.get('market_regime', 'UNKNOWN'),
                    'edge': float(_oa_conf_pct) / 100.0,
                    'probability': float(_oa_conf_pct) / 100.0,
                    'market_space': float(snapshot.get('quality_score', 0) or 0) / 100.0,
                    'execution_quality': _exec_quality,
                    'regime_fit': _regime_fit,
                }, daily_pnl=0.0, consecutive_losses=0, regime_clear=True)
            except Exception:
                pass

            # =================================================================
            # PHASE 3 — INSTITUTIONAL SHADOW ARCHITECTURE
            # Runs as a fully independent sidecar after core decision.
            # Does NOT modify runtime_decision, snapshot, or any core state.
            # Any error here is caught and logged — never affects trading.
            # =================================================================
            if _PHASE3_AVAILABLE and _candidate_id:
                try:
                    _p3_open_trades = []
                    try:
                        from core.portfolio_risk_authority import get_portfolio_state
                        _p3_open_trades = list(get_portfolio_state().open_trades or [])
                    except Exception:
                        pass

                    _p3_input = Phase3Input(
                        candidate_id=_candidate_id or "",
                        strategy=snapshot.get('decision_context', {}).strategy
                            if hasattr(snapshot.get('decision_context', {}), 'strategy')
                            else snapshot.get('strategy', 'SMC'),
                        signal=snapshot.get('decision_context', {}).signal
                            if hasattr(snapshot.get('decision_context', {}), 'signal')
                            else snapshot.get('signal', 'NONE'),
                        symbol=SYMBOL,
                        quality_score=float(snapshot.get('quality_score', 0) or 0),
                        confidence_pct=float(
                            snapshot.get('confidence', {}).get('pct', 50) or 50
                        ),
                        composite_score=float(
                            snapshot.get('decision_context', {}).get('composite_score', 50)
                            if isinstance(snapshot.get('decision_context', {}), dict)
                            else getattr(snapshot.get('decision_context', {}), 'composite_score', 50)
                            or 50
                        ),
                        actual_decision=str(_mode_val or 'UNKNOWN'),
                        open_trades=_p3_open_trades,
                        account_balance=float(_account_balance() or 1000),
                        equity=float(_account_balance() or 1000),
                        session=str(snapshot.get('session', 'UNKNOWN') or 'UNKNOWN'),
                        market_regime=str(snapshot.get('market_regime', 'UNKNOWN') or 'UNKNOWN'),
                        ml_score=float(
                            snapshot.get('ml', {}).get('score', 50)
                            if isinstance(snapshot.get('ml'), dict)
                            else 50
                        ),
                        gold_macro_factors=None,  # سيُضاف لاحقاً من data feed
                    )
                    _p3_out = run_phase3_shadow(_p3_input)
                    _last_phase3_shadow_decision = _p3_out.final_brain_decision
                    _last_phase3_ml_timestamp = _p3_input.timestamp

                except Exception as _p3_err:
                    print(f"[PHASE3] Shadow cycle error (non-fatal): {_p3_err}")
            # =================================================================
            # END PHASE 3 SHADOW
            # =================================================================

            # =================================================================
            # V3.0.1-SLTP-FIXED: LOSS-PAUSE GUARD
            # بعد خسارتين متتاليتين → انتظر إشارة CHoCH/BOS جديدة
            # =================================================================
            history_sync = {}
            try:
                history_sync = sync_mt5_history()
                if history_sync.get('error'):
                    raise RuntimeError(history_sync['error'])
                _register_confirmed_close_events(history_sync)
                if history_sync.get('close_events'):
                    try:
                        from core.exit_manager import resolve_exit_outcomes
                        _exit_result = resolve_exit_outcomes(
                            _resolver_candles_cache
                        )
                        if not _exit_result.get('ok'):
                            print(
                                '[EXIT_SHADOW] Outcome resolver deferred: '
                                f"{_exit_result.get('reason', 'unknown reason')}"
                            )
                    except Exception as _exit_shadow_error:
                        print(
                            f'⚠️ EXIT_SHADOW_RESOLUTION_FAILED: '
                            f'{_exit_shadow_error}'
                        )
                    try:
                        sync_csv_to_truth_layer()
                        from analytics.truth_layer import persist_daily_report
                        from analytics.setup_analyzer import persist_setup_analysis_report
                        persist_daily_report()
                        _setup_report = persist_setup_analysis_report()
                        print(
                            '[TRADE_ANALYTICS] close outcomes updated | '
                            f"closed={len(history_sync['close_events'])} "
                            f"strategies={len(_setup_report.get('strategies', {}))}"
                        )
                    except Exception as _analytics_error:
                        print(f'⚠️ TRADE_ANALYTICS_REFRESH_FAILED: {_analytics_error}')
                    try:
                        from analytics.shadow_system_report import persist_shadow_system_report
                        shadow_report = persist_shadow_system_report()
                        print(
                            '[SHADOW_SYSTEM_REVIEW] refreshed after close | '
                            f"decisions_due={shadow_report['summary']['decision_required_count']}"
                        )
                    except Exception as _shadow_report_error:
                        print(
                            '⚠️ SHADOW_SYSTEM_REVIEW_FAILED after close: '
                            f'{_shadow_report_error}'
                        )
            except Exception as exc:
                print(f'🛑 CLOSE_SYNC_BLOCK | cannot confirm recent MT5 closes: {exc}')
                time.sleep(CHECK_INTERVAL)
                continue

            loss_pause = evaluate_loss_pause(
                snapshot_or_symbol=snapshot,
                market_regime=snapshot.get('market_regime'),
            )
            if not loss_pause.get('trading_allowed', True):
                print(
                    f'V3-FIXED blocked: LOSS_PAUSE_GUARD active — '
                    f'{loss_pause.get("reason", "")}'
                )
                # skip rest of cycle, but still run post-sync, watchdog, etc.
                regime = snapshot.get('market_regime')
                try:
                    update_certification_progress()
                except Exception:
                    pass
                try:
                    metrics_pair = analyze_trades()
                    metrics = metrics_pair[1] if isinstance(metrics_pair, tuple) else {}
                    write_daily_performance_report(metrics=metrics)
                except Exception:
                    pass
                loss_pause_status = get_loss_pause_status()
                telegram_status = check_telegram_health()
                run_watchdog_cycle(
                    mt5_available=MT5_AVAILABLE,
                    memory_available=True,
                    telegram_available=telegram_status["available"],
                    cpu_ok=True,
                    db_ok=True,
                    production_ready=_system_startup_ready,
                    signal_quality=int(snapshot.get('quality_score', 0)),
                    process_alive=True,
                    cpu_percent=0.0,
                    disk_ok=True,
                    loop_frozen=False,
                    feed_ok=snapshot.get('tick') is not None,
                    ram_ok=True,
                    ram_percent=0.0,
                    rss_mb=0.0,
                    rss_growth_mb=0.0,
                    ai_memory_healthy=True,
                    ai_memory_rows=0,
                    db_latency_ms=0.0,
                    telegram_latency_ms=telegram_status["latency_ms"] or 0.0,
                    loop_latency_sec=time.time() - loop_start,
                    historical_degradation=1 if loss_pause_status.get('pause_active') else 0,
                )
                time.sleep(CHECK_INTERVAL)
                continue

            # Reconcile before evaluating the primary strategy so position
            # state is fresh for risk checks.
            if MT5_AVAILABLE and mt5 is not None:
                try:
                    _live_positions_pre_runners = mt5.positions_get(symbol=SYMBOL)
                    if _live_positions_pre_runners is not None:
                        _reconcile_result_pre = reconcile_with_live_positions(_live_positions_pre_runners)
                        _removed_pre = _reconcile_result_pre.get('removed', 0)
                        _imported_pre = _reconcile_result_pre.get('imported', 0)
                        if _removed_pre or _imported_pre:
                            print(f'🔧 PRE-RUNNER RECONCILE | removed={_removed_pre} imported={_imported_pre}')
                except Exception as exc:
                    print(f'⚠️ pre-runner reconciliation (non-fatal): {exc}')
            
            # ─────────────────────────────────────────────────────────────
            # FER3ON ARCHITECTURE FIX #1: SNAPSHOT FRESHNESS
            # Before SMC execution, rebuild snapshot to ensure prices, ATR,
            # and market structure reflect current market state (not 5+ sec old).
            # The primary strategy gets fresh data before execution.
            # ─────────────────────────────────────────────────────────────
            if runtime_decision.get('approved'):
                try:
                    snapshot_fresh = _build_live_snapshot(
                        SYMBOL,
                        strategy=active_strategy,
                    )
                    if (
                        snapshot_fresh
                        and snapshot_fresh.get('ready') is True
                        and snapshot_fresh.get('signal') == snapshot.get('signal')
                        and snapshot_fresh.get('strategy') == active_strategy
                        and isinstance(snapshot_fresh.get('quality_gate'), dict)
                        and isinstance(snapshot_fresh.get('execution'), dict)
                    ):
                        snapshot = snapshot_fresh
                        print(f'[FRESHNESS] Snapshot refreshed | Price: {snapshot.get("entry_price", 0):.2f} | ATR: {snapshot.get("atr", 0):.2f}')
                    elif snapshot_fresh:
                        print('[FRESHNESS] Signal, strategy, or fields changed; retaining authority-reviewed snapshot')
                except Exception as _snapshot_refresh_err:
                    print(f'⚠️ [FRESHNESS] Snapshot refresh failed (using stale): {_snapshot_refresh_err}')

            lot = 0  # Initialize lot before use
            if runtime_decision.get('approved'):
                # ─────────────────────────────────────────────────────────
                # SIZE-TIER RESOLUTION — authority gates EXECUTION,
                # quality and execution grade determine LOT SIZE TIER.
                #
                # Rule:  authority  → sole arbiter of whether to execute
                #        quality    → sets the lot-size tier (FULL/REDUCED/MICRO)
                #        execution  → further refines lot via exec_grade in
                #                     calculate_smart_lot (unchanged)
                #
                # When authority says FULL but quality says EXECUTE_REDUCED,
                # we execute at REDUCED — not FULL, not blocked.
                # When execution grade is REJECT, we fall back to MICRO tier
                # but still execute (authority approved; exec_grade passed
                # through to calculate_smart_lot which will apply its own
                # multiplier — it does NOT zero out lot for REJECT grade).
                # ─────────────────────────────────────────────────────────
                _TIER_RANK = {'MICRO': 0, 'REDUCED': 1, 'FULL': 2}
                _QUALITY_TIER_MAP = {
                    'STRICT_PASS':     'FULL',
                    'EXECUTE_FULL':    'FULL',
                    'ADAPTIVE_PASS':   'REDUCED',
                    'EXECUTE_REDUCED': 'REDUCED',
                    'EXECUTE_MICRO':   'MICRO',
                    'REJECT':          'MICRO',   # authority overrides; minimum tier
                }
                _auth_mode = runtime_decision.get('mode', 'MICRO')
                _qual_raw  = snapshot['quality_gate'].get('mode', 'REJECT')
                _qual_mode = _QUALITY_TIER_MAP.get(_qual_raw, 'MICRO')
                # Take the most conservative (smallest rank) of the two
                _effective_mode = (
                    _auth_mode
                    if _TIER_RANK.get(_auth_mode, 0) <= _TIER_RANK.get(_qual_mode, 0)
                    else _qual_mode
                )
                _smc_confirmed = bool(snapshot.get('smc_confirmed', False))
                _smc_grade = str(snapshot.get('entry_grade', 'NONE') or 'NONE').upper()
                _candle = snapshot.get('candle') or {}
                _candle_gate = _candle.get('gate_v3') or {}
                _two_candle_confirmation = bool(
                    _candle_gate.get('m5_aligned')
                    and _candle_gate.get('m15_aligned')
                )
                strategy_confirmation = (
                    _smc_confirmed and bool(_candle.get('confirmed'))
                    if active_strategy == 'DAILY'
                    else _smc_confirmed and _two_candle_confirmation
                )
                if not strategy_confirmation:
                    _effective_mode = 'REDUCED'
                if _smc_grade == 'NONE':
                    _effective_mode = 'MICRO'
                _exec_grade_used = snapshot['execution'].get('grade', 'C')
                _exec_approved   = snapshot['execution'].get('approved', False)
                print(
                    f'V3-FIXED sizing: auth={_auth_mode} | qual={_qual_raw}→{_qual_mode} '
                    f'| effective={_effective_mode} '
                    f'| strategy={active_strategy} confirmed={strategy_confirmation} '
                    f'| exec_grade={_exec_grade_used} exec_approved={_exec_approved}'
                )

                # =============================================================
                # PHASE 5 — OPPORTUNITY ALLOCATOR INTEGRATION (already evaluated centrally)
                # Use the pre-computed _central_opp_rank from before runners were invoked.
                # This ensures SMC uses the same ranking as other strategies.
                # =============================================================
                _opp_rank = _central_opp_rank
                _risk_multiplier_from_allocator = 1.0

                if _PHASE5_ALLOCATOR_AVAILABLE and _opp_rank is not None:
                    print(f"[PHASE5-SMC] Using central ranking | Grade: {_opp_rank.grade} | Score: {_opp_rank.score:.0f}")
                    _risk_multiplier_from_allocator = effective_risk_adjustment(
                        _opp_rank,
                        live_enabled=PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED,
                    )

                    if _opp_rank.should_reject:
                        if PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED:
                            print(f"[PHASE5] ALLOCATOR_REJECT | {_opp_rank.reasoning}")
                            print('FINAL_DECISION: REJECTED_BY_ALLOCATOR')
                            time.sleep(CHECK_INTERVAL)
                            continue
                        print(
                            f"[PHASE5] ADVISORY_WEAK | {_opp_rank.reasoning}"
                            " | live sizing unchanged"
                        )
                    else:
                        if PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED:
                            print(f"[PHASE5] Applying sizing: risk_mult={_risk_multiplier_from_allocator:.2f}")
                        else:
                            print("[PHASE5] ADVISORY_ONLY | live sizing unchanged")

                # FER3ON FINAL [EXPOSURE-3]: was `round(max(0.10, min(0.75,
                # 0.50 * risk_multiplier)), 3)` — a hardcoded 0.50% base with
                # no connection to settings.RISK_PER_TRADE_PERCENT. On this
                # account's $200-$1000 range that meant every real value here
                # (0.10-0.75%) was too small for calculate_smart_lot's
                # MIN_LOT_RISK_GUARD to ever pass at $200 — it would silently
                # skip every SMC trade. Now anchored to the same single
                # source of truth as every other strategy, floored so it
                # can't silently stop trading. See FER3ON_FINAL_CHANGELOG.md
                # [EXPOSURE-3].
                _auth_risk_mult = float(runtime_decision.get('risk_multiplier', 0.5) or 0.5)
                _combined_risk_mult = _auth_risk_mult * _risk_multiplier_from_allocator
                risk_percent = round(max(
                    MIN_EFFECTIVE_RISK_PERCENT,
                    min(MAX_RISK_TOTAL, RISK_PER_TRADE_PERCENT * _combined_risk_mult)
                ), 3)

                # =========================================================
                # POSITION CHECK & AUTHORITY GATE
                # =========================================================
                positions = mt5.positions_get(symbol=SYMBOL) if MT5_AVAILABLE else None

                # FER3ON FINAL [SAFETY-1]: positions_get() returned None means MT5 state is unknown.
                # This is not "safe to proceed" — it's "data unavailable, must not trade".
                # Fail-closed: treat None/False as a hard block, never assume zero positions.
                if MT5_AVAILABLE and positions is None:
                    print(f'🛑 POSITION_CHECK_FAILED | MT5 state unknown, blocking trade (fail-closed)')
                    time.sleep(CHECK_INTERVAL)
                    continue

                same_direction_count = 0
                if positions:
                    signal_type = snapshot['signal']
                    for pos in positions:
                        if (
                            signal_type == "BUY"
                            and pos.type == mt5.POSITION_TYPE_BUY
                        ):
                            same_direction_count += 1
                        elif (
                            signal_type == "SELL"
                            and pos.type == mt5.POSITION_TYPE_SELL
                        ):
                            same_direction_count += 1

                    if same_direction_count >= MAX_SAME_DIRECTION_POSITIONS:
                        print(
                            f"🚫 MAX SAME DIRECTION REACHED ({same_direction_count}/{MAX_SAME_DIRECTION_POSITIONS})"
                        )
                        time.sleep(CHECK_INTERVAL)
                        continue

                # =========================================================
                # V3.5 PHASE-1 FIX: Portfolio Risk Authority gate.
                # evaluate_risk() MUST be called BEFORE calculate_smart_lot()
                # to ensure final_risk_percent is used for lot sizing.
                # Previously this was called AFTER lot sizing, which meant
                # lot could exceed what the authority actually approved.
                # =========================================================
                # Keep the in-memory authority synchronized with the broker
                # balance before it evaluates any risk limits. The snapshot
                # may have been built earlier in the heartbeat, and the
                # account can change after a closed trade.
                current_live_balance = _live_account_balance()
                if current_live_balance is None:
                    print('🛑 ACCOUNT_BALANCE_CHECK_FAILED | MT5 balance unavailable, blocking trade (fail-closed)')
                    time.sleep(CHECK_INTERVAL)
                    continue
                snapshot['balance'] = current_live_balance
                sync_portfolio_equity(current_live_balance)

                risk_decision = evaluate_risk(
                    strategy=active_strategy,
                    direction=snapshot['signal'],
                    requested_risk_percent=risk_percent,
                    candidate_meta={'symbol': SYMBOL},
                    ml_advice_boost=0.0,
                    ml_advice_enabled=False,
                )
                try:
                    from analytics.authority_impact import record_risk_decision
                    record_risk_decision(
                        strategy=active_strategy, direction=snapshot['signal'],
                        requested_risk_percent=risk_percent, decision=risk_decision,
                    )
                except Exception as _impact_log_err:
                    print(f'⚠️ AUTHORITY_IMPACT_LOG_FAILED (non-fatal): {_impact_log_err}')
                if not risk_decision.approved:
                    print(f"🛑 PORTFOLIO_RISK_BLOCK | {risk_decision.rejection_reason} | {risk_decision.notes}")
                    time.sleep(CHECK_INTERVAL)
                    continue
                
                # FER3ON FINAL [EXPOSURE-4]: Authority computes final_risk_percent based on
                # position limits, daily/weekly loss caps, and other portfolio constraints.
                # Use this computed value instead of the nominal risk_percent that was
                # requested before the authority's constraints were applied.
                # This ensures lot sizing is consistent with what the authority actually approved.
                final_risk_for_sizing = float(risk_decision.final_risk_percent or risk_percent)
                if final_risk_for_sizing != risk_percent:
                    print(f'🔧 RISK_ADJUSTED | requested={risk_percent:.3f}% → approved={final_risk_for_sizing:.3f}% by authority')
                    risk_percent = final_risk_for_sizing

                # ═════════════════════════════════════════════════════════════
                # ARCHITECTURE FIX #5: CONSISTENCY VALIDATION
                # The broker balance was synchronized immediately before the
                # authority gate. Keep this check as a diagnostic guard only;
                # never replace a fresh broker value with stale in-memory data.
                # ═════════════════════════════════════════════════════════════
                try:
                    from core.portfolio_risk_authority import get_portfolio_state
                    _portfolio = get_portfolio_state()
                    _snapshot_balance = float(snapshot.get('balance', 0) or 0)
                    _authority_balance = float(_portfolio.current_equity or 0)
                    
                    if abs(_snapshot_balance - _authority_balance) > 1.0:  # Tolerance: $1
                        print(f'⚠️ [CONSISTENCY] Balance mismatch | snapshot=${_snapshot_balance:.2f} != authority=${_authority_balance:.2f}')
                        print(f'   Broker balance retained as ground truth; authority will resync next cycle')
                except Exception as _consistency_err:
                    print(f'⚠️ [CONSISTENCY] Check failed (non-fatal): {_consistency_err}')

                # NOW calculate lot using the authority-approved risk_percent
                lot, raw_lot, lot_adjustments = calculate_smart_lot(
                    balance=snapshot['balance'],
                    risk_percent=risk_percent,
                    sl_dist=snapshot['sl_dist'],
                    symbol=SYMBOL,
                    quality_score=snapshot['quality_score'],
                    session=snapshot['session'],
                    recovery_mode=False,
                    exec_grade=_exec_grade_used,
                    ai_score=snapshot['ml'].get('ml_score', 50),
                    brain_score=snapshot['brain'].get('master_score', 50),
                    session_score=snapshot['decision_context'].context_score,
                    aggression_mode='SMART',
                    strategy=active_strategy,
                    market_regime=snapshot['market_regime'],
                    size_mode=_effective_mode,
                )
                print(f'POSITION SIZING | raw_lot={raw_lot} final_lot={lot} adjustments={lot_adjustments}')
                if lot > MAX_LOT:
                    lot = MAX_LOT
                    print(f'🛡 LOT_CAPPED | to MAX_LOT={MAX_LOT}')

                if _cooldown_active_for(active_strategy):
                    print(f"🛑 COOLDOWN_BLOCK | {active_strategy} | {TRADE_COOLDOWN}s window")
                    time.sleep(CHECK_INTERVAL)
                    continue

                if lot > 0 and MT5_AVAILABLE and SHADOW_ONLY_RUNTIME:
                    _virtual_id = _candidate_id
                    try:
                        from analytics.shadow_counterfactual import log_virtual_shadow
                        if _virtual_id and _virtual_id not in _virtual_shadow_seen:
                            _virtual_logged = log_virtual_shadow({
                                'signal_id': _virtual_id,
                                'candidate_id': _candidate_id,
                                'symbol': SYMBOL,
                                'direction': snapshot.get('signal', 'NONE'),
                                'signal_time': datetime.now(timezone.utc).isoformat(),
                                'entry_price': float(snapshot.get('entry_price', current_price) or current_price),
                                'sl_dist': float(snapshot.get('sl_dist', 0) or 0),
                                'tp_dist': float(snapshot.get('tp_dist', 0) or 0),
                                'atr': float(snapshot.get('atr', 0) or 0),
                                'regime': snapshot.get('market_regime', 'UNKNOWN'),
                                'session': snapshot.get('session', 'UNKNOWN'),
                                'strategy': active_strategy,
                                'confidence': (snapshot.get('confidence') or {}).get('pct', 0) if isinstance(snapshot.get('confidence'), dict) else snapshot.get('confidence', 0),
                                'quality_score': snapshot.get('quality_score', 0),
                                'config_revision': 'recovery_atr_v1',
                                'sltp_mode': 'ATR_PROFILE',
                                'virtual_reason': 'SHADOW_ONLY_RUNTIME',
                            })
                            if _virtual_logged:
                                _virtual_shadow_seen.add(_virtual_id)
                                _virtual_shadow_failed.discard(_virtual_id)
                            elif _virtual_id not in _virtual_shadow_failed:
                                print(f'⚠️ VIRTUAL_SHADOW_LOG_ERROR: record was not persisted for signal {_virtual_id}; will retry')
                                _virtual_shadow_failed.add(_virtual_id)
                    except Exception as _virtual_shadow_err:
                        if _virtual_id not in _virtual_shadow_failed:
                            print(f'⚠️ VIRTUAL_SHADOW_LOG_ERROR: {_virtual_shadow_err}; will retry signal {_virtual_id}')
                            _virtual_shadow_failed.add(_virtual_id)

                if lot > 0 and MT5_AVAILABLE and not SHADOW_ONLY_RUNTIME:

                    request = _build_order_request(
                        snapshot['signal'],
                        lot,
                        snapshot['sl_dist'],
                        snapshot['tp_dist'],
                        atr=snapshot.get('atr', 0.0),
                        strategy=active_strategy,
                        tick=snapshot.get('tick'),
                    )

                    _snap_structure = snapshot.get('structure') or {}
                    _snap_structure_analysis = snapshot.get('structure_analysis') or {}
                    _snap_liquidity = snapshot.get('liquidity') or {}
                    _liq_bias = _snap_liquidity.get('bias')
                    _liq_map_dir = 'UP' if _liq_bias == 'BUY' else 'DOWN' if _liq_bias == 'SELL' else 'NEUTRAL'
                    from core.trade_event_ledger import (
                        append_trade_event,
                        create_trade_correlation_id,
                    )
                    _stop_diagnostics = snapshot.get('adaptive_sltp') or {}
                    _stop_anchor = _stop_diagnostics.get('selected_stop_anchor') or {}
                    _decision_id = create_trade_correlation_id(
                        symbol=SYMBOL,
                        strategy=active_strategy,
                        signal=snapshot['signal'],
                        decision_bar_time=snapshot.get('decision_bar_time'),
                        entry_price=request.get('price'),
                        stop_loss=request.get('sl'),
                        take_profit=request.get('tp'),
                    )
                    _entry_attribution = build_entry_attribution(
                        snapshot, runtime_decision
                    )
                    append_trade_event(
                        'DECISION',
                        _decision_id,
                        candidate_id=_candidate_id or None,
                        symbol=SYMBOL,
                        strategy=active_strategy,
                        signal=snapshot['signal'],
                        decision_bar_time=snapshot.get('decision_bar_time'),
                        atr=float(snapshot.get('atr', 0) or 0),
                        entry_price=request.get('price'),
                        stop_loss=request.get('sl'),
                        take_profit=request.get('tp'),
                        stop_source=_stop_diagnostics.get('selected_stop_source'),
                        stop_anchor=_stop_anchor,
                        stop_selection_reason=_stop_diagnostics.get('stop_selection_reason'),
                        stop_reason=_stop_diagnostics.get('stop_reason'),
                        stop_buffer=_stop_diagnostics.get('structure_buffer'),
                        entry_reason=_entry_attribution['entry_reason'],
                        entry_conditions=_entry_attribution['entry_conditions'],
                        entry_evidence=_entry_attribution['entry_evidence'],
                    )

                    result = execute_trade(
                        request=request,
                        strategy=active_strategy,
                        signal=snapshot['signal'],
                        lot=lot,
                        sl_dist=snapshot['sl_dist'],
                        tp_dist=snapshot['tp_dist'],
                        rr_ratio=snapshot['execution'].get('rr_ratio', 0),
                        risk_percent=risk_percent,
                        exec_grade=_exec_grade_used,
                        final_brain={'final_score': snapshot['brain'].get('master_score', 50)},
                        quality_score=snapshot['quality_score'],
                        confidence=snapshot['confidence'],
                        market_regime=snapshot['market_regime'],
                        atr=snapshot['atr'],
                        session=snapshot['session'],
                        magic=DAILY_MAGIC if active_strategy == 'DAILY' else SMC_MAGIC,
                        tp_tiers=snapshot.get('tp_tiers'),
                        choch_state=_snap_structure.get('structure', 'UNKNOWN'),
                        choch_strength=_snap_structure_analysis.get('choch_strength', 'WEAK'),
                        liq_map_score=_snap_liquidity.get('score', 0),
                        liq_map_dir=_liq_map_dir,
                        mtf_strength=snapshot.get('mtf_strength', 0),
                        mtf_structural=1 if _snap_structure.get('mtf_aligned') else 0,
                        size_mode=_effective_mode,
                        decision_id=_decision_id,
                        stop_diagnostics=_stop_diagnostics,
                        entry_reason=_entry_attribution['entry_reason'],
                        entry_conditions=_entry_attribution['entry_conditions'],
                        entry_evidence=_entry_attribution['entry_evidence'],

                    )
                    append_trade_event(
                        'DECISION_EXECUTION_RESULT',
                        _decision_id,
                        retcode=(
                            result.get('retcode')
                            if isinstance(result, dict)
                            else getattr(result, 'retcode', None)
                        ),
                        comment=(
                            result.get('comment')
                            if isinstance(result, dict)
                            else getattr(result, 'comment', None)
                        ),
                        order_ticket=(
                            result.get('order')
                            if isinstance(result, dict)
                            else getattr(result, 'order', None)
                        ),
                        deal_ticket=(
                            result.get('deal')
                            if isinstance(result, dict)
                            else getattr(result, 'deal', None)
                        ),
                        fill_price=(
                            result.get('price')
                            if isinstance(result, dict)
                            else getattr(result, 'price', None)
                        ),
                        fill_volume=(
                            result.get('volume')
                            if isinstance(result, dict)
                            else getattr(result, 'volume', None)
                        ),
                    )

                    if result is not None and getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
                        filled_lot = get_filled_volume(result, request.get('volume', lot))
                        print(f'✅ TRADE OPENED | ticket={result.order} lot={filled_lot}')
                        _register_trade_opened(active_strategy)
                        if snapshot.get('session') == 'OFF_HOURS':
                            _register_off_hours_trade()
                        
                        # =================================================================
                        # SMART COUNTER-TRADING ADVISORY [FER3ON-FIX-2026-09-02]
                        # After opening primary trade, evaluate if a counter position
                        # would be beneficial based on strong signal bias.
                        # This is ADVISORY ONLY — logged but not auto-executed to avoid
                        # increasing exposure during high-bias periods.
                        # =================================================================
                        if _SMART_COUNTER_AVAILABLE:
                            try:
                                _counter_pos = get_counter_position(
                                    original_signal=snapshot['signal'],
                                    original_lot=filled_lot,
                                    original_sl=snapshot['sl_dist'],
                                    original_tp=snapshot['tp_dist'],
                                )
                                if _counter_pos and _counter_pos.get('enabled'):
                                    print(
                                        f'[SMART-COUNTER-ADVISORY] | Signal: {_counter_pos["counter_signal"]} | '
                                        f'Lot: {_counter_pos["counter_lot"]} | '
                                        f'Confidence: {_counter_pos["confidence"]} | '
                                        f'{_counter_pos["reasoning"]}'
                                    )
                                    # تسجيل الاستشارة (للتحليل اللاحق)
                                    # لكن لا تنفذ تلقائياً الآن (التنفيذ اختياري يدوي)
                                    log_counter_trade(snapshot['signal'], _counter_pos)
                            except Exception as _counter_trading_err:
                                print(f"⚠️ [SMART-COUNTER] Advisory calculation failed (non-fatal): {_counter_trading_err}")
                        
                        try:
                            _entry_price_val = float(getattr(result, 'price', 0) or 0)
                            _sl_price_val = float(request.get('sl', 0) or 0)
                            _realized_risk_pct = compute_realized_risk_percent(
                                lot=filled_lot,
                                entry_price=_entry_price_val,
                                sl_price=_sl_price_val,
                                balance=_account_balance(),
                            )
                            record_trade_open(
                                ticket=int(result.order),
                                strategy=active_strategy,
                                direction=snapshot['signal'],
                                lot=filled_lot,
                                # FER3ON FINAL [EXPOSURE-1]: record the ACTUAL
                                # realized risk (from final lot + SL), not the
                                # nominal pre-sizing risk_percent — see
                                # FER3ON_FINAL_CHANGELOG.md [EXPOSURE-1].
                                risk_percent=_realized_risk_pct,
                                entry_price=_entry_price_val,
                                sl=_sl_price_val,
                                tp=float(request.get('tp', 0) or 0),
                                symbol=SYMBOL,
                                meta={'quality_score': snapshot['quality_score'], 'session': snapshot.get('session')},
                            )
                        except Exception as exc:
                            print(f'⚠️ record_trade_open failed: {exc}')
                    else:
                        _skip_comment = None
                        _skip_retcode = None
                        if isinstance(result, dict):
                            _skip_comment = result.get("comment")
                            _skip_retcode = result.get("retcode")
                        else:
                            _skip_comment = getattr(result, "comment", None)
                            _skip_retcode = getattr(result, "retcode", None)
                        print(
                            f"V3-FIXED execution skipped | reason={_skip_comment or 'UNKNOWN'}"
                            f" retcode={_skip_retcode}"
                        )
                else:
                    # lot=0 (sizing computed zero) or MT5 not available — not a policy block.
                    print(
                        f'V3-FIXED skip: lot={lot:.3f} MT5_AVAILABLE={MT5_AVAILABLE}'
                        f' | effective_mode={_effective_mode} exec_grade={_exec_grade_used}'
                    )
            else:
                # Authority rejected — the sole legitimate block path.
                _block_reason = (
                    runtime_decision.get('hard_block_reason')
                    or runtime_decision.get('reason')
                    or 'AUTHORITY_REJECTED'
                )
                print(f'V3-FIXED blocked: AUTHORITY | {_block_reason}')

            try:
                certification = update_certification_progress()
                analytics_result = analyze_trades()
                metrics = analytics_result[1] if isinstance(analytics_result, tuple) else {}
                write_daily_performance_report(metrics=metrics)
            except Exception as exc:
                print(f'Post-cycle sync warning: {exc}')
                history_sync = {}
                certification = {}

            # =================================================================
            # PHASE 3 — Notify trade close (updates STRATEGY_DNA, FINAL_BRAIN)
            # =================================================================
            if _PHASE3_AVAILABLE:
                for closed_event in history_sync.get('close_events', []):
                    try:
                        _phase3_notify_trade_closed(
                            ticket=int(closed_event.get('ticket') or 0),
                            strategy=str(closed_event.get('strategy') or 'UNKNOWN'),
                            session=str(snapshot.get('session', 'UNKNOWN') or 'UNKNOWN'),
                            regime=str(snapshot.get('market_regime', 'UNKNOWN') or 'UNKNOWN'),
                            was_winner=closed_event.get('result') == 'WIN',
                            profit=float(closed_event.get('profit') or 0.0),
                            shadow_final_brain_decision=_last_phase3_shadow_decision,
                            ml_prediction_timestamp=_last_phase3_ml_timestamp,
                        )
                    except Exception as _p3_close_err:
                        print(f"[PHASE3] Trade close notify error (non-fatal): {_p3_close_err}")
            # =================================================================
            # END PHASE 3 TRADE CLOSE
            # =================================================================

            quota = get_quota_state()
            ai_memory_rows = int(certification.get('closed_trade_count', 0) or 0)
            
            # =================================================================
            # SMART COUNTER-TRADING SUMMARY [FER3ON-FIX-2026-09-02]
            # Log periodic counter-trading stats for monitoring
            # =================================================================
            if _SMART_COUNTER_AVAILABLE and counter % 100 == 0:  # Every 100 cycles
                try:
                    _ct_summary = get_counter_trading_summary()
                    if _ct_summary.get('total_counter_trades', 0) > 0:
                        print(
                            f"[SMART-COUNTER] Summary | "
                            f"Total: {_ct_summary['total_counter_trades']} | "
                            f"Wins: {_ct_summary['wins']} | "
                            f"SR: {_ct_summary['success_rate']}% | "
                            f"Avg Conf: {_ct_summary['avg_confidence']}"
                        )
                except Exception as _ct_summary_err:
                    print(f"⚠️ [SMART-COUNTER] Summary calculation failed: {_ct_summary_err}")
            
            telegram_status = check_telegram_health()
            run_watchdog_cycle(
                mt5_available=MT5_AVAILABLE,
                memory_available=True,
                telegram_available=telegram_status["available"],
                cpu_ok=True,
                db_ok=True,
                production_ready=_system_startup_ready,
                signal_quality=int(snapshot['quality_score']),
                process_alive=True,
                cpu_percent=0.0,
                disk_ok=True,
                loop_frozen=False,
                feed_ok=snapshot.get('tick') is not None,
                ram_ok=True,
                ram_percent=0.0,
                rss_mb=0.0,
                rss_growth_mb=0.0,
                ai_memory_healthy=True,
                ai_memory_rows=ai_memory_rows,
                db_latency_ms=0.0,
                telegram_latency_ms=telegram_status["latency_ms"] or 0.0,
                loop_latency_sec=time.time() - loop_start,
                historical_degradation=0 if quota.get('remaining_total', 0) > 0 else 1,
            )

            # ═════════════════════════════════════════════════════════════
            # ARCHITECTURE FIX #6: ADAPTIVE SLEEP FOR REDUCED LATENCY
            # If heartbeat processing took N seconds, sleep for
            # (CHECK_INTERVAL - N) instead of fixed CHECK_INTERVAL.
            # This reduces per-cycle latency from 65 sec to ~60 sec when
            # processing is slow, and allows faster re-entry when idle.
            # ═════════════════════════════════════════════════════════════
            cycle_elapsed = time.time() - loop_start
            if SHADOW_RUN_MAX_CYCLES and counter >= SHADOW_RUN_MAX_CYCLES:
                print(f'Runtime cycle limit reached: {counter}. Exiting safely.')
                break
            adaptive_sleep = max(1.0, CHECK_INTERVAL - cycle_elapsed)  # Min 1 second
            if cycle_elapsed > 5.0:  # Only log if processing was slow
                print(f"[LATENCY] Cycle: {cycle_elapsed:.1f}s | Sleeping: {adaptive_sleep:.1f}s")
            time.sleep(adaptive_sleep)
    except KeyboardInterrupt:
        print('\nShutdown requested. Exiting.')


if __name__ == '__main__':
    main()