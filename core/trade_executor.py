# =========================================
# FER3ON V3 — TRADE EXECUTOR (HARDENED v3-FIXED)
# المكوّنات المُدمجة:
#   - V2.2 OPERATIONAL: البنية الأساسية (سجلات/تتبع/memory)
#   - V2.2 INVALID:    UNSUPPORTED_FILLING_RETCODE=10030
#                      + _is_unsupported_filling()
#                      + get_filling_fallback_sequence()
#   - V3 P3c:          _enforce_min_stop_distance()
#                      (بُنيت من الصفر — غير موجودة في source)
#   - V3-FIXED:        إصلاح broker stop_level calculation
#                      + إرجاع corrected sl_dist للـ caller
# =========================================

import json
import math
import threading
from datetime import datetime, timezone
from typing import Optional

from core.mt5_compat import mt5, MT5_AVAILABLE
from core.ai_memory import save_trade_memory
from core.settings import (
    MAX_SL_DISTANCE_DOLLARS,
    get_min_sl_dollars,
    BROKER_STOP_LEVEL_FALLBACK,
    MAX_DAILY_TRADES,
    ORDER_RETRY_ON_STOPS_REJECTION_ENABLED,
    ORDER_RETRY_STEP_PCT,
    ORDER_RETRY_MAX_ATTEMPTS,
    ORDER_RETRY_REJECTION_RETCODES,
    ORDER_RETRY_MAX_WIDEN_FACTOR,
    MAX_SL_DISTANCE_DOLLARS,
    BUILD_ID,
    # AUDIT FIX [CERT-6] (re-applied on top of REARCH-1/2): STEP 3 below used
    # to hardcode the per-strategy cap as a bare `>= 1` instead of reading
    # this. See CERT-6 in docs/history/FER3ON_FINAL_CHANGELOG.md. This fix
    # was dropped when the rearch-phase1-2 branch forked from a pre-CERT-6
    # snapshot; merged back in manually alongside REARCH-1/2/3/4.
    MAX_OPEN_PER_STRATEGY,
    PER_STRATEGY_MAX_OPEN_LIMITS,
    MAX_OPEN_PER_SYMBOL_DIRECTION,
    ENABLE_CROSS_STRATEGY_HEDGE,
    MAX_CROSS_STRATEGY_HEDGES,
    TRADE_EXECUTOR_LOG_PATH,
)
from core.test_mode_manager import register_trade as register_test_mode_trade
from core.trade_logger import log_trade as persist_trade_log
from core.trade_identity import resolve_trade_identity, strategy_from_magic
from core.mt5_order_utils import get_filling_fallback_sequence
from core.structured_logging import StructuredLogger


_EXECUTOR_LOGGER = StructuredLogger(
    log_path=TRADE_EXECUTOR_LOG_PATH,
    console=False,
)


def _log_executor_exception(event: str, exc: Exception, **extra) -> None:
    """Persist critical executor failures without weakening fail-closed gates."""
    try:
        _EXECUTOR_LOGGER.error(
            event,
            {"exception_type": type(exc).__name__, "exception": str(exc), **extra},
        )
    except Exception:
        return


# =========================================
# GLOBAL LIVE DAILY TRADE COUNTER  (V3-FIX: حد 50 صفقة يومي فعلي)
# FER3ON FINAL: sourced from core.settings.MAX_DAILY_TRADES instead of a
# separate hardcoded literal, so there is one single source of truth for
# the daily trade cap (build spec Action Plan #1 / [EXEC-1]). Previously
# this was a hardcoded 100 that would silently diverge from settings.py.
# =========================================

_live_trade_day = None
_live_trade_count = 0
MAX_LIVE_DAILY_TRADES = MAX_DAILY_TRADES
_EXECUTION_LOCK = threading.RLock()


def _reset_live_daily_counter_if_needed():
    global _live_trade_day, _live_trade_count
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _live_trade_day != today:
        _live_trade_day = today
        _live_trade_count = 0


def _live_daily_cap_hit():
    _reset_live_daily_counter_if_needed()
    return _live_trade_count >= MAX_LIVE_DAILY_TRADES


def _synchronized_execution(function):
    def wrapper(*args, **kwargs):
        with _EXECUTION_LOCK:
            return function(*args, **kwargs)
    return wrapper


def _register_live_trade():
    global _live_trade_count
    _reset_live_daily_counter_if_needed()
    _live_trade_count += 1


def _required_min_stop_distance(symbol: str, point: float = 0.01) -> float:
    """Return the broker and application minimum in raw price units."""
    floor = get_min_sl_dollars(point)
    fallback = float(BROKER_STOP_LEVEL_FALLBACK) * point
    if MT5_AVAILABLE and mt5 is not None:
        try:
            info = mt5.symbol_info(symbol)
            if info is not None:
                stop_level = int(getattr(info, "trade_stops_level", 0) or 0)
                if stop_level > 0:
                    return max(floor, stop_level * point)
                return max(floor, fallback)
        except Exception as exc:
            print(f"⚠️ BROKER_MIN_STOP READ FAILED: {exc}")
    return max(floor, fallback)


def get_filled_volume(result, fallback=0.0):
    """Return the executed volume, falling back to the sent request if absent."""
    candidates = [getattr(result, "volume", None)]
    result_request = getattr(result, "request", None)
    if isinstance(result_request, dict):
        candidates.append(result_request.get("volume"))
    else:
        candidates.append(getattr(result_request, "volume", None))
    candidates.append(fallback)

    for candidate in candidates:
        if candidate is None:
            continue
        try:
            volume = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(volume) and volume > 0:
            return volume
    return 0.0


# =========================================
# UNSUPPORTED FILLING DETECTOR  (من V2.2 INVALID — P2-A)
# =========================================

UNSUPPORTED_FILLING_RETCODE = 10030


def _is_unsupported_filling(response):
    if response is None:
        return False
    retcode = getattr(response, 'retcode', None)
    comment = str(getattr(response, 'comment', '') or '').lower()
    return retcode == UNSUPPORTED_FILLING_RETCODE or 'unsupported filling mode' in comment


# =========================================
# STOPS-TOO-CLOSE REJECTION DETECTOR (ported from V9FINAL1 — build spec
# Merge item #1 / FER3ON_FINAL_CHANGELOG.md [EXEC-1])
# =========================================


def _is_stops_too_close_rejection(response):
    """
    Detects a broker rejection because SL/TP are too close to the current
    price (unrelated to filling mode). retcodes 10016 (Invalid stops), 10017
    and 10006 are covered via ORDER_RETRY_REJECTION_RETCODES in
    core/settings.py to support different brokers.
    """
    if response is None:
        return False
    retcode = getattr(response, 'retcode', None)
    comment = str(getattr(response, 'comment', '') or '').lower()
    return (
        retcode in ORDER_RETRY_REJECTION_RETCODES
        or 'invalid stops' in comment
        or 'stops too close' in comment
    )


# =========================================
# MIN STOP DISTANCE ENFORCER  (V3.0.1-SLTP-FIXED)
# إجبار SL على ألا يقل عن MIN_SL_DISTANCE=30 + broker stop_level + fallback آمن
# =========================================


def _enforce_min_stop_distance(symbol: str, sl_dist: float, point: float = 0.01) -> float:
    """Apply only the final safety floor for broker stop-level constraints.

    The adaptive engine already computes the real SL distance from ATR and
    market context. Broker stop level is only used as a protective floor when
    the exchange requires a minimum distance; it is not used as a primary basis
    for the calculation.

    FER3ON FINAL BUGFIX [SLTP-1]: `sl_dist` (this function's input, coming
    from core.adaptive_sl_tp_engine.calculate_adaptive_sl_tp) is in RAW PRICE
    UNITS (e.g. $29.35 for gold) — confirmed by core/trailing_stop.py, which
    does `new_sl = current_price - trailing_distance` with NO point
    multiplication, and current_price is an absolute MT5 price. MIN_SL_DISTANCE
    (a "points" setting, e.g. 1500 = $15 for gold) was being compared directly
    against sl_dist WITHOUT the `* point` conversion applied two lines below to
    BROKER_STOP_LEVEL_FALLBACK in this very function — so `floor` was always
    1500, always dwarfing a real sl_dist of ~$15-90, and this function always
    returned 1500 instead of the adaptive value. In practice this meant the
    adaptive SL engine's output was discarded on every single trade for any
    tier where MIN_SL_DISTANCE >= ~100, replacing it with a flat, non-adaptive
    stop. See FER3ON_FINAL_CHANGELOG.md [SLTP-1] for the full trace (this bug
    predates this merge — it is not something introduced by the V9FINAL1
    execution-retry merge).
    """
    # [REARCH-1]: was `float(MIN_SL_DISTANCE) * point` inline here -- same
    # formula used by the entry path's pre-adaptive-engine floor, but
    # written independently, which is exactly the kind of two-copies setup
    # that let [SLTP-1] happen in the first place. Both now call the one
    # function in core/settings.py.
    floor = _required_min_stop_distance(symbol, point)

    if sl_dist is None or float(sl_dist or 0) <= 0:
        print(f'🛑 HIGH_FIX_6: Invalid SL distance sl_dist={sl_dist}, using floor={floor}')
        return floor
    enforced = max(float(sl_dist), floor)
    # FER3ON FINAL [SLTP-2]: cap the adaptive stop for this account size —
    # see settings.py MAX_SL_DISTANCE_DOLLARS for the full reasoning
    # (MIN_LOT granularity means an uncapped ATR spike would force an
    # oversized single-trade risk that no risk_percent setting can fix).
    if enforced > MAX_SL_DISTANCE_DOLLARS:
        print(
            f'🛡 MAX_SL_CAPPED | adaptive/floor sl_dist={enforced:.2f} > '
            f'MAX_SL_DISTANCE_DOLLARS={MAX_SL_DISTANCE_DOLLARS} — capping'
        )
        enforced = MAX_SL_DISTANCE_DOLLARS
    return enforced


def _enforce_min_tp_distance(
    sl_dist_final: float,
    tp_dist: Optional[float],
    strategy: Optional[str] = None,
    sl_dist_original: Optional[float] = None,
) -> float:
    """Keep TP proportional to the SL that is ACTUALLY placed on the order.

    FER3ON FINAL BUGFIX [SLTP-3]: this used to be a floor ONLY (tp >=
    sl_dist_final). That is correct when sl_dist never changes, but
    _enforce_min_stop_distance (see MAX_SL_DISTANCE_DOLLARS above) very
    often rewrites sl_dist to a smaller, fixed value — while tp_dist was
    computed by the adaptive engine against the ORIGINAL, larger sl_dist
    (tp_distance = sl_distance * risk_reward, see
    core/adaptive_sl_tp_engine.py). Leaving tp_dist untouched after that
    meant the numerator (TP) and denominator (SL) of the risk:reward ratio
    stopped referring to the same stop — e.g. an intended 1:1.8 trade with
    an original $40 SL / $72 TP would ship as a real $10 SL / $72 TP
    (~1:7.2), which is exactly the "SL nearly fixed at 1000 points, TP
    hugely oversized" behaviour reported in practice.

    Fix: when we know what the SL was BEFORE it got capped/floored
    (sl_dist_original), we recompute the intended RR from the original
    pair and re-apply that SAME ratio to the real, enforced SL. This keeps
    whatever risk:reward the adaptive engine actually decided on (based on
    confluence/quality/session/etc.), just scaled to the stop that is truly
    at risk, instead of leaving TP anchored to a stop distance that no
    longer exists.
    
    CRITICAL FIX #2: Added division-by-zero guard before computing intended_rr.
    """
    if tp_dist is None:
        return float(sl_dist_final)

    sl_dist_final = float(sl_dist_final)
    tp_dist = float(tp_dist)

    if sl_dist_original and float(sl_dist_original) > 0:
        sl_dist_original = float(sl_dist_original)
        # CRITICAL FIX #2: Guard against division by zero
        if sl_dist_original <= 0:
            print(f'🛑 DIVISION_BY_ZERO_GUARD: sl_dist_original={sl_dist_original}, skipping RR rescale')
            return max(float(tp_dist), float(sl_dist_final))
        intended_rr = tp_dist / sl_dist_original
        rescaled_tp = sl_dist_final * intended_rr
        # Still keep an absolute floor: TP must never end up <= the real SL.
        final_tp = max(rescaled_tp, sl_dist_final)
        if abs(final_tp - tp_dist) > 1e-6:
            print(
                f'🛡 TP_RESCALED | sl_original={sl_dist_original:.2f} → '
                f'sl_final={sl_dist_final:.2f} | rr_kept={intended_rr:.2f} | '
                f'tp_original={tp_dist:.2f} → tp_final={final_tp:.2f}'
            )
        return final_tp

    # Fallback: no original SL supplied, behave as a pure safety floor
    # (previous behaviour) rather than guessing a ratio.
    final_tp = max(tp_dist, sl_dist_final)
    if final_tp != tp_dist:
        print(f'🛡 TP_FLOOR | was_tp={tp_dist} → now_tp={final_tp}')
    return final_tp


def enforce_and_return_min_stop(symbol: str, sl_dist: float, point: float = 0.01) -> float:
    return _enforce_min_stop_distance(symbol, sl_dist, point)


# =========================================
# STOPS-REJECTION RETRY (ported from V9FINAL1 trade_executor.py — build spec
# Merge item #1 / FER3ON_FINAL_CHANGELOG.md [EXEC-1])
#
# UNIT NOTE (CORRECTED — see FER3ON_FINAL_CHANGELOG.md [SLTP-1]): sl_dist/
# tp_dist are RAW PRICE UNITS (e.g. $29.35 for gold), confirmed by
# core/trailing_stop.py's `new_sl = current_price - trailing_distance` with
# no point multiplication. They are used directly against `price` below —
# NOT multiplied by `point`. (V9FINAL1's original version also added
# sl_dist/tp_dist directly, so this ends up matching V9FINAL1's convention,
# not diverging from it as an earlier version of this comment assumed.)
# =========================================


def _cap_retry_growth(growth, sl_dist_raw, sl_cap=None):
    """FER3ON Phase-0: cap the stops-retry widening factor so a retried
    order can NEVER carry more risk than the account-size cap allows.

    Uncapped, ORDER_RETRY_STEP_PCT=0.10 with MAX_ATTEMPTS=5 widens SL by
    1.10^4 ≈ 1.61x — e.g. a $30 gold stop becomes $48, silently breaking
    the MAX_SL_DISTANCE_DOLLARS contract the finalizer just enforced.
    The effective factor is the TIGHTEST of:
      1. the requested geometric growth,
      2. ORDER_RETRY_MAX_WIDEN_FACTOR,
      3. the context-aware final SL cap / original sl_dist.
    Same capped factor is applied to BOTH sl and tp so the RR ratio the
    finalizer chose is preserved (TP is never left behind while SL grows).
    """
    try:
        # Keep retry widening within the cap consumed by finalize_sl_tp.
        from core.settings import MAX_SL_DISTANCE_DOLLARS as FINALIZER_SL_CAP
        base = float(sl_dist_raw)
        if base <= 0:
            return max(1.0, float(growth))
        effective_cap = min(
            float(FINALIZER_SL_CAP),
            float(sl_cap) if sl_cap is not None else float(FINALIZER_SL_CAP),
        )
        capped = min(
            float(growth),
            float(ORDER_RETRY_MAX_WIDEN_FACTOR),
            effective_cap / base,
        )
        return max(1.0, capped)
    except (TypeError, ValueError, OverflowError):
        return 1.0


def _send_order_with_stops_retry(
    request,
    symbol,
    point,
    sl_dist,
    tp_dist,
    price,
    signal,
    sl_cap=None,
    decision_id=None,
    strategy=None,
):
    """
    If the broker rejects the order because SL/TP are too close to price,
    resend with SL/TP widened progressively (×10% per attempt by default)
    until the broker accepts it or ORDER_RETRY_MAX_ATTEMPTS is reached. This
    is independent from the filling-mode fallback loop below (a different
    rejection class entirely — proximity to price, not order-fill type) and
    wraps it so every widening level still tries every filling mode.

    Returns: (result, final_sl_dist, final_tp_dist). result may be None if
    every attempt failed (same failure behaviour as before this merge).
    """
    current_sl_dist = float(sl_dist)
    current_tp_dist = float(tp_dist)
    max_attempts = ORDER_RETRY_MAX_ATTEMPTS if ORDER_RETRY_ON_STOPS_REJECTION_ENABLED else 1

    last_result = None
    last_check = None

    for retry_index in range(max_attempts):
        if retry_index > 0:
            growth = (1.0 + ORDER_RETRY_STEP_PCT) ** retry_index
            growth = _cap_retry_growth(growth, sl_dist, sl_cap=sl_cap)
            current_sl_dist = round(float(sl_dist) * growth, 2)
            current_tp_dist = round(float(tp_dist) * growth, 2)
            print(
                f'🔁 STOPS_RETRY | attempt={retry_index + 1}/{max_attempts}'
                f' | widening ×{growth:.3f}'
                f' | sl_dist={current_sl_dist} tp_dist={current_tp_dist}'
            )

        # Rebuild SL/TP in the request at the current (original or widened)
        # distance. sl_dist/tp_dist are RAW PRICE UNITS — used directly.
        retry_request = dict(request)
        if price > 0:
            if str(retry_request.get('type')).startswith('1'):  # SELL
                retry_request['sl'] = round(price + current_sl_dist, 5)
                retry_request['tp'] = round(price - current_tp_dist, 5)
            else:  # BUY
                retry_request['sl'] = round(price - current_sl_dist, 5)
                retry_request['tp'] = round(price + current_tp_dist, 5)

        # Inner filling-mode fallback loop (pre-existing — different rejection class)
        result = None
        for attempt_index, filling_mode in enumerate(
            get_filling_fallback_sequence(retry_request.get('type_filling'))
        ):
            trial_request = dict(retry_request)
            trial_request['type_filling'] = filling_mode

            if attempt_index > 0:
                print(
                    f'🔁 FILLING FALLBACK | retry={attempt_index + 1}'
                    f' | type_filling={filling_mode}'
                )

            check = mt5.order_check(trial_request)
            last_check = check

            if check is None:
                print('❌ ORDER CHECK FAILED')
                continue

            if _is_unsupported_filling(check):
                print(
                    f'⚠️ ORDER CHECK REJECTED FILLING MODE'
                    f' | type_filling={filling_mode}'
                )
                continue

            from core.trade_event_ledger import append_trade_event
            append_trade_event(
                "ORDER_SEND_ATTEMPT",
                decision_id,
                symbol=symbol,
                strategy=strategy,
                attempt=retry_index + 1,
                filling_mode=filling_mode,
                volume=trial_request.get("volume"),
                price=trial_request.get("price"),
                stop_loss=trial_request.get("sl"),
                take_profit=trial_request.get("tp"),
                comment=trial_request.get("comment"),
            )
            try:
                print(
                    f"📤 ORDER SEND REQUEST | symbol={trial_request.get('symbol')}"
                    f" volume={trial_request.get('volume')}"
                    f" price={trial_request.get('price')}"
                    f" sl={trial_request.get('sl')} tp={trial_request.get('tp')}"
                )
                result = mt5.order_send(trial_request)
            except Exception as e:
                print(f'❌ ORDER SEND EXCEPTION: {e}')
                continue

            if result is None:
                print('❌ ORDER_SEND RETURNED NONE')
                continue

            if _is_unsupported_filling(result):
                print(
                    f'⚠️ ORDER SEND REJECTED FILLING MODE'
                    f' | type_filling={filling_mode}'
                )
                result = None
                continue

            retry_request.update({'type_filling': filling_mode})
            break

        last_result = result

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            if retry_index > 0:
                print(f'✅ STOPS_RETRY_SUCCEEDED | attempt={retry_index + 1}')
            return result, current_sl_dist, current_tp_dist

        if result is not None and not _is_stops_too_close_rejection(result):
            # Rejected for a reason other than stops proximity (insufficient
            # margin, market closed, etc.) — widening further won't help.
            print(
                f'❌ EXECUTION FAILED (non-stops reason, no retry)'
                f' | retcode={result.retcode}'
            )
            return result, current_sl_dist, current_tp_dist

        if not ORDER_RETRY_ON_STOPS_REJECTION_ENABLED:
            break

    if last_result is not None:
        print(f'❌ STOPS_RETRY_EXHAUSTED | max_attempts={max_attempts} reached')
        return last_result, current_sl_dist, current_tp_dist

    if last_check is not None and _is_unsupported_filling(last_check):
        print('❌ EXECUTION FAILED | all filling modes rejected by broker')
        return last_check, current_sl_dist, current_tp_dist

    print('❌ EXECUTION FAILED | no order result')
    return None, current_sl_dist, current_tp_dist


def _check_per_strategy_limit(mt5_module, symbol, magic, max_open_per_strategy):
    """Isolated, directly-testable version of STEP 3 below.

    Returns (blocked: bool, same_strategy_open: int). Counts open positions
    on `symbol` sharing `magic` and blocks once that count reaches
    `max_open_per_strategy`.

    AUDIT FIX [CERT-6] (docs/history/FER3ON_FINAL_CHANGELOG.md): this used
    to hardcode `>= 1` inline in execute_trade() instead of reading
    settings.MAX_OPEN_PER_STRATEGY, so the config value existed but the
    check that actually runs at order-send time silently ignored it.
    Pulled out into its own function so this specific check -- the real
    per-strategy enforcement, alongside core.portfolio_risk_authority's own
    MAX_OPEN_PER_STRATEGY check earlier in the pipeline -- can be unit
    tested without needing to drive the rest of execute_trade(). See CERT-6
    for why core.risk_manager.evaluate_position_limits()'s per-strategy
    soft limits (now sourced from settings.PER_STRATEGY_SOFT_POSITION_LIMITS
    per REARCH-2) are NOT this
    cap.
    """
    positions_all = mt5_module.positions_get(symbol=symbol)
    if positions_all is None:
        raise RuntimeError("POSITION_STATE_UNAVAILABLE")
    this_magic = int(magic or 0)
    same_strategy_open = sum(
        1 for pos in positions_all if int(getattr(pos, "magic", 0) or 0) == this_magic
    )
    return same_strategy_open >= max_open_per_strategy, same_strategy_open


def _check_hedge_policy(mt5_module, symbol, current_type, strategy):
    positions_all = mt5_module.positions_get(symbol=symbol)
    if positions_all is None:
        raise RuntimeError("POSITION_STATE_UNAVAILABLE")
    opposite_type = (
        mt5_module.POSITION_TYPE_SELL
        if current_type == mt5_module.ORDER_TYPE_BUY
        else mt5_module.POSITION_TYPE_BUY
    )
    opposite_positions = [
        pos for pos in positions_all
        if getattr(pos, "type", None) == opposite_type
    ]
    if not opposite_positions:
        return False, 0
    if not ENABLE_CROSS_STRATEGY_HEDGE:
        return True, len(opposite_positions)

    account = mt5_module.account_info()
    hedging_mode = getattr(mt5_module, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2)
    if account is None or getattr(account, "margin_mode", None) != hedging_mode:
        return True, len(opposite_positions)

    current_strategy = str(strategy or "UNKNOWN").upper()
    same_strategy = any(
        strategy_from_magic(getattr(pos, "magic", None), default="UNKNOWN")
        == current_strategy
        for pos in opposite_positions
    )
    return same_strategy or len(opposite_positions) >= MAX_CROSS_STRATEGY_HEDGES, len(opposite_positions)


def _check_symbol_direction_limit(mt5_module, symbol, signal, max_open):
    positions_all = mt5_module.positions_get(symbol=symbol)
    if positions_all is None:
        raise RuntimeError("POSITION_STATE_UNAVAILABLE")
    target_direction = str(signal or '').upper()
    buy_type = getattr(mt5_module, 'POSITION_TYPE_BUY', 0)
    same_direction_open = sum(
        1 for pos in positions_all
        if (
            target_direction == 'BUY' and getattr(pos, 'type', None) == buy_type
        ) or (
            target_direction == 'SELL' and getattr(pos, 'type', None) != buy_type
        )
    )
    return same_direction_open >= max_open, same_direction_open


# =========================================
# EXECUTE TRADE
# =========================================


@_synchronized_execution
def execute_trade(
    request,
    strategy,
    signal,
    lot,
    sl_dist,
    tp_dist,
    rr_ratio,
    risk_percent,
    exec_grade,
    final_brain,
    quality_score,
    confidence,
    market_regime,
    atr,
    session,
    magic,
    tp_tiers=None,
    mtf_alignment_mode="ALIGNED",
    v7_confidence_bonus=0.0,
    choch_state=None,
    choch_strength=None,
    liq_map_score=None,
    liq_map_dir=None,
    mtf_strength=None,
    mtf_structural=None,
    size_mode=None,
    decision_id=None,
    stop_diagnostics=None,
    entry_reason=None,
    entry_conditions=None,
    entry_evidence=None,
):
    print('=' * 80)
    print('📤 INITIAL ORDER REQUEST')

    # Ensure we have a strategy key available for downstream adjustments
    _strat_key = str(strategy or 'UNKNOWN')
    initial_lot = max(0.0, float(request.get('volume', lot) or 0.0))
    from core.trade_event_ledger import (
        append_trade_event,
        build_mt5_trade_comment,
        create_trade_correlation_id,
    )
    if not decision_id:
        decision_id = create_trade_correlation_id(
            symbol=request.get("symbol"),
            strategy=_strat_key,
            signal=signal,
            decision_bar_time=datetime.now(timezone.utc).isoformat(),
            entry_price=request.get("price"),
            stop_loss=request.get("sl"),
            take_profit=request.get("tp"),
        )
    decision_id = str(decision_id)
    request["comment"] = build_mt5_trade_comment(_strat_key, decision_id)
    append_trade_event(
        "EXECUTION_REQUESTED",
        decision_id,
        symbol=request.get("symbol"),
        strategy=_strat_key,
        signal=signal,
        volume=request.get("volume"),
        price=request.get("price"),
        stop_loss=request.get("sl"),
        take_profit=request.get("tp"),
        magic=request.get("magic") or magic,
        stop_diagnostics=stop_diagnostics or {},
        entry_reason=entry_reason or "",
        entry_conditions=entry_conditions or [],
        entry_evidence=entry_evidence or {},
    )

    # Enforce the loss pause at the final execution authority as well as in
    # the main loop. This closes alternate runner paths and race windows.
    try:
        from core.loss_pause_guard import evaluate_loss_pause
        pause_state = evaluate_loss_pause(
            {'symbol': request.get('symbol'), 'signal': signal},
            market_regime=market_regime,
        )
        if not pause_state.get('trading_allowed', True):
            return {'retcode': -10, 'comment': 'LOSS_PAUSE_GUARD_ACTIVE'}
        loss_streak = int(pause_state.get('consecutive_losses', 0) or 0)
    except Exception as exc:
        _log_executor_exception('LOSS_PAUSE_CHECK_FAILED', exc, strategy=_strat_key)
        print(f'🛑 LOSS_PAUSE_CHECK_FAILED (fail-closed): {exc}')
        return {'retcode': -10, 'comment': 'LOSS_PAUSE_CHECK_FAILED'}

    # =========================================
    # [FER3ON-FIX-2026-08-19] STRATEGY KILL-SWITCH
    # data-driven pre-trade block based on 120 real closed trades.
    # Blocks toxic session/regime/exec_grade combos + daily/weekly loss caps.
    # =========================================
    try:
        from core.strategy_kill_switch import should_block_trade
        _block, _reason = should_block_trade(
            strategy=_strat_key,
            session=session,
            market_regime=market_regime,
            exec_grade=exec_grade,
            size_mode=size_mode,
        )
        if _block:
            print(f'\xf0\x9f\x9a\xab KILL_SWITCH_BLOCK | {_reason}')
            return {'retcode': -1, 'comment': _reason}
    except Exception as _ks_exc:
        _log_executor_exception('KILL_SWITCH_CHECK_FAILED', _ks_exc, strategy=_strat_key)
        # [FER3ON-FIX-2026-08-21] كان قبل كده "non-fatal, allowing trade" —
        # يعني أي خطأ في فحص الحماية نفسه كان بيسمح بالصفقة بدل ما يمنعها.
        # ده عكس مبدأ fail-closed المطلوب لمكوّن حماية حرج. الاستثناء دلوقتي
        # يمنع الصفقة، زي بالظبط لو should_block_trade رجّعت True صراحة.
        _reason = f'KILL_SWITCH_CHECK_FAILED_FAIL_CLOSED_{type(_ks_exc).__name__}'
        print(f'\xf0\x9f\x9a\xab KILL_SWITCH_CHECK_FAILED (fail-closed, blocking trade): {_ks_exc}')
        return {'retcode': -1, 'comment': _reason}

    from core.demo_execution import demo_execution_status
    _demo_allowed, _demo_reason = demo_execution_status()
    if not _demo_allowed:
        print(f'🛑 ORDER_BLOCKED | {_demo_reason}')
        return {'retcode': -20, 'comment': _demo_reason}

    for k, v in request.items():
        print(f'{k}: {v}')

    # ----- V3.0.1: معلومات وقف/هدف بعد التعديل -----
    try:
        _type = str(request.get('type', ''))
        _price = float(request.get('price', 0) or 0)
        _sl = float(request.get('sl', 0) or 0)
        _tp = float(request.get('tp', 0) or 0)
        if _price > 0 and _sl > 0 and _tp > 0:
            _sl_d = abs(_price - _sl)
            _tp_d = abs(_price - _tp)
            _rr = round(_tp_d / _sl_d, 2) if _sl_d > 0 else 0.0
            print(f'🛡 SL/TP DISTANCE | sl_dist_points=${_sl_d:.2f} tp_dist_points=${_tp_d:.2f} RR={_rr}')
    except Exception as _exc:
        print(f'⚠️ SL/TP distance log failed: {_exc}')

    print('=' * 80)

    price = float(request.get('price', 0) or 0)
    sl = float(request.get('sl', 0) or 0)
    tp = float(request.get('tp', 0) or 0)

    if sl <= 0 or tp <= 0:
        print('⚠️ TRADE_REJECTED | MISSING_SL_TP')
        return {'retcode': -1, 'comment': 'MISSING_SL_TP'}

    sl_dist_pts = abs(price - sl)
    tp_dist_pts = abs(tp - price)
    rr_guard = (tp_dist_pts / sl_dist_pts) if sl_dist_pts > 0 else 0.0

    # =========================================
    # [FER3ON-FIX-2026-08-19] EXPECTED EDGE GATE
    # Reject any trade whose (WR * RR) - (1-WR) has no positive edge.
    # Uses real historical win_rate from data/history/trades.csv per strategy.
    # =========================================
    try:
        from core.expected_edge_gate import should_reject_by_edge
        _reject, _edge_reason, _ev_ratio = should_reject_by_edge(
            strategy=_strat_key,
            risk_reward=rr_guard,
            sl_distance=sl_dist_pts,
        )
        if _reject:
            print(f'\xf0\x9f\x9a\xab EDGE_GATE_REJECT | {_edge_reason}')
            return {'retcode': -1, 'comment': _edge_reason}
        else:
            print(f'\xe2\x9c\x85 EDGE_GATE_PASS | ev_ratio={_ev_ratio:+.3f}')
    except Exception as _ee_exc:
        _log_executor_exception('EDGE_GATE_CHECK_FAILED', _ee_exc, strategy=_strat_key)
        print(f'🛑 EDGE_GATE_CHECK_FAILED (fail-closed): {_ee_exc}')
        return {'retcode': -8, 'comment': 'EDGE_GATE_CHECK_FAILED'}


    # The RR is now computed dynamically by the adaptive engine; no fixed RR
    # floor should reject a trade at execution time.
    if sl_dist_pts <= 0 or tp_dist_pts <= 0:
        print('⚠️ TRADE_REJECTED | MISSING_SL_TP_DISTANCE')
        return {'retcode': -1, 'comment': 'MISSING_SL_TP_DISTANCE'}

    # =========================================
    # V6: QUANT ENGINE — تعديل اللوت الفعلي بناءً على أداء الاستراتيجية
    # التاريخي الحقيقي (Sharpe/Sortino/Recovery Factor من analytics/quant_engine.py)
    #
    # نقطة دمج متعمَّدة هنا تحديدًا: execute_trade هي نقطة الالتقاء الفعلية
    # الوحيدة في مسار فتح الصفقات — بعكس unified_decide/
    # calculate_adaptive_lot التي لا يستدعيها فعليًا إلا مسار SMC جزئيًا.
    #
    # CRITICAL: يجب تعديل request['volume'] هنا، لا فقط متغير lot المحلي —
    # trial_request = dict(request) أدناه هو ما يُرسَل فعليًا لـ mt5.order_send،
    # وهو منفصل تمامًا في الذاكرة عن متغير lot (تعديل lot وحده كان سيكون بلا
    # أي أثر فعلي على الصفقة المُرسلة، رغم ظهوره في السجلات والذاكرة).
    # لا حظر أبدًا — فقط تصغير/تكبير اللوت (QUANT_MIN_RISK_MULTIPLIER كحد أدنى).
    # =========================================
    try:
        from analytics.quant_engine import evaluate_strategy_health
        health = evaluate_strategy_health(_strat_key)
        health_tier = str(health.health_tier or 'UNKNOWN').upper()
        if health.risk_multiplier != 1.0:
            _lot_before = float(lot)
            lot = round(float(lot) * health.risk_multiplier, 2)
            lot = max(lot, 0.01)  # لا يصفّر أبدًا
            request['volume'] = float(lot)
            print(
                f"📊 QUANT_LOT_ADJUST | {_strat_key} | tier={health.health_tier}"
                f" | lot {_lot_before} → {lot} (×{health.risk_multiplier})"
            )
    except Exception as exc:
        health_tier = 'UNKNOWN'
        _log_executor_exception('QUANT_ENGINE_LOT_ADJUST_FAILED', exc, strategy=_strat_key)
        print(f'⚠️ QUANT_ENGINE_LOT_ADJUST_FAILED (non-fatal, lot unchanged): {exc}')

    # =========================================
    # V7: EXECUTION INTELLIGENCE — تكبير لوت محدود جدًا عند زخم سعري قوي
    # (core/v7_integration.py + core/velocity_engine.py — كود ناضج وموجود
    # مسبقًا، اكتُشف أنه معزول تمامًا عن main.py، تم ربطه هنا).
    #
    # v7_confidence_bonus comes from the execution-context analysis.
    #
    # "جريء لكن غير متهور": سقف صريح ضيق جدًا (V7_MAX_LOT_BOOST) — هذا بونص
    # تكبير، لا عقوبة تصغير، فالحذر مطلوب هنا أكثر من V6 (V6 يحمي من أداء
    # ضعيف مؤكَّد إحصائيًا؛ V7 يراهن على زخم لحظي، احتمال خطأ أعلى نسبيًا).
    # =========================================
    try:
        v7_bonus = float(v7_confidence_bonus or 0.0)
        if v7_bonus > 0:
            from core.settings import V7_MAX_LOT_BOOST
            boost_factor = 1.0 + min(v7_bonus / 100.0, V7_MAX_LOT_BOOST)
            _lot_before_v7 = float(lot)
            lot = round(float(lot) * boost_factor, 2)
            request['volume'] = float(lot)
            if lot != _lot_before_v7:
                print(
                    f"⚡ V7_VELOCITY_BOOST | {_strat_key} | bonus={v7_bonus:.1f}"
                    f" | lot {_lot_before_v7} → {lot} (×{boost_factor:.3f})"
                )
    except Exception as exc:
        _log_executor_exception('V7_LOT_BOOST_FAILED', exc, strategy=_strat_key)
        print(f'⚠️ V7_LOT_BOOST_FAILED (non-fatal, lot unchanged): {exc}')

    # =========================================
    # V7-PLUS: REGIME STRATEGY FIT (core/market_regime.py) — "اختيار
    # الاستراتيجية المناسبة حسب حالة السوق" المطلوب في خريطة الطريق، لكن
    # كأوزان مرنة لا تشغيل/إيقاف ثنائي صلب (get_strategy_for_regime القديمة
    # كانت ستعني عمليًا حظر 3 من 4 استراتيجيات حسب الحالة — رُفضت لمخالفتها
    # فلسفة "لا حظر، مرونة"). كل الاستراتيجيات نشطة دائمًا، فقط حجمها يتكيف
    # مع ملاءمتها لحالة السوق الحالية (TRENDING/RANGING/VOLATILE/CRISIS).
    # =========================================
    try:
        from core.market_regime import get_regime_fit_multiplier
        regime_fit = get_regime_fit_multiplier(_strat_key, market_regime)
        if regime_fit != 1.0:
            _lot_before_regime = float(lot)
            lot = round(float(lot) * regime_fit, 2)
            lot = max(lot, 0.01)  # لا يصفّر أبدًا
            request['volume'] = float(lot)
            if lot != _lot_before_regime:
                print(
                    f"🌍 REGIME_FIT_ADJUST | {_strat_key} | regime={market_regime}"
                    f" | lot {_lot_before_regime} → {lot} (×{regime_fit:.2f})"
                )
    except Exception as exc:
        _log_executor_exception('REGIME_FIT_ADJUST_FAILED', exc, strategy=_strat_key)
        print(f'⚠️ REGIME_FIT_ADJUST_FAILED (non-fatal, lot unchanged): {exc}')

    # =========================================
    # V9: SHADOW READINESS BRIDGE (analytics/v9_readiness_bridge.py) — تأثير
    # تدريجي صغير جدًا مبني على جاهزية FINAL_BRAIN (Shadow Learning)، بدون
    # لمس core/phase3/ أو الـ assert الذي يحرسه. تحت العتبة الدنيا الحالية
    # (راجع v9_readiness_bridge.py للأرقام الفعلية) التأثير = صفر تمامًا.
    # هذا متعمَّد: النظام لم يثبت موضوعيًا جاهزيته الكاملة بعد (يُقاس بالكود
    # نفسه، لا بالتخمين)، فالتأثير الحالي محايد حتى تتراكم دورات Shadow كافية.
    # =========================================
    try:
        from analytics.v9_readiness_bridge import compute_v9_lot_multiplier
        v9_result = compute_v9_lot_multiplier()
        v9_mult = float(v9_result.get('lot_multiplier', 1.0))
        if v9_mult != 1.0:
            _lot_before_v9 = float(lot)
            lot = round(float(lot) * v9_mult, 2)
            lot = max(lot, 0.01)
            request['volume'] = float(lot)
            if lot != _lot_before_v9:
                print(
                    f"🧠 V9_LOT_ADJUST | readiness={v9_result.get('readiness_score', 0):.1f}"
                    f" | lot {_lot_before_v9} → {lot} (×{v9_mult:.3f})"
                )
    except Exception as exc:
        _log_executor_exception('V9_READINESS_BRIDGE_FAILED', exc, strategy=_strat_key)
        print(f'⚠️ V9_READINESS_BRIDGE_FAILED (non-fatal, lot unchanged): {exc}')

    # Final volume boundary after all quant/V7/regime/readiness adjustments.
    # No downstream multiplier may exceed the configured account ceiling.
    try:
        from core.settings import MAX_LOT
        if loss_streak > 0 or health_tier in {'WEAK', 'POOR'}:
            request['volume'] = min(float(request.get('volume', lot) or 0.0), initial_lot)
        request['volume'] = min(
            float(MAX_LOT), max(0.0, float(request.get('volume', lot) or 0.0))
        )
        lot = request['volume']
        if lot <= 0:
            return {'retcode': -9, 'comment': 'FINAL_LOT_INVALID'}
    except Exception as exc:
        _log_executor_exception('FINAL_LOT_BOUNDARY_FAILED', exc, strategy=_strat_key)
        print(f'🛑 FINAL_LOT_BOUNDARY_FAILED: {exc}')
        return {'retcode': -9, 'comment': 'FINAL_LOT_BOUNDARY_FAILED'}

    if request.get('type_filling') not in (0, 1, 2):
        try:
            request['type_filling'] = mt5.ORDER_FILLING_IOC
        except Exception:
            pass

    if not MT5_AVAILABLE or mt5 is None:
        print('⚠️ LIVE EXECUTION BLOCKED | MT5 unavailable')
        return None

    # =========================================
    # STEP 1: حقن magic الصح + comment في الطلب (مركزي لكل الاستراتيجيات)
    # =========================================
    try:
        identity = resolve_trade_identity(strategy=strategy, magic=magic)
        request["magic"] = int(identity["magic"])
        request["comment"] = build_mt5_trade_comment(
            str(identity["strategy"]), decision_id
        )
        print(
            f"🏷 MAGIC INJECTED | strategy={identity['strategy']}"
            f" | magic={identity['magic']}"
        )
    except Exception as e:
        print(f"⚠️ MAGIC INJECTION FAILED: {e}")

    # =========================================
    # STEP 2: conditional cross-strategy hedge protection
    # =========================================
    try:
        symbol = request.get("symbol")
        current_type = request.get("type")
        hedge_blocked, opposite_count = _check_hedge_policy(
            mt5, symbol, current_type, strategy
        )
        if hedge_blocked:
            print(
                f"🚫 HEDGE_BLOCKED | strategy={strategy}"
                f" opposite_positions={opposite_count}"
            )
            return {"retcode": -3, "comment": "HEDGE_POLICY_BLOCKED"}

    except Exception as e:
        print(f"🛑 HEDGE CHECK FAILED (fail-closed): {e}")
        return {"retcode": -6, "comment": "HEDGE_CHECK_FAILED"}

    # =========================================
    # STEP 3: صفقة واحدة لكل استراتيجية (تحقق بالـ magic مش بالاتجاه)
    # =========================================
    # AUDIT FIX [CERT-6]: this used to hardcode `>= 1` instead of reading
    # settings.MAX_OPEN_PER_STRATEGY, so the config value existed but this
    # -- the check that actually runs at order-send time -- silently ignored
    # it. Behavior is unchanged today (MAX_OPEN_PER_STRATEGY == 1), but this
    # now genuinely tracks the config instead of only pretending to. See
    # CERT-6 in docs/history/FER3ON_FINAL_CHANGELOG.md for the full context,
    # including why core.risk_manager.evaluate_position_limits()'s
    # per-strategy soft limits are NOT the real per-strategy cap -- this check (and
    # core.portfolio_risk_authority's own MAX_OPEN_PER_STRATEGY check,
    # evaluated earlier in the pipeline) are.
    try:
        symbol = request.get("symbol")
        this_magic = int(request.get("magic", 0))
        blocked, same_strategy_open = _check_per_strategy_limit(
            mt5,
            symbol,
            this_magic,
            int(PER_STRATEGY_MAX_OPEN_LIMITS.get(str(strategy or '').upper(), MAX_OPEN_PER_STRATEGY)),
        )

        if blocked:
            print(
                f"🚫 PER_STRATEGY_LIMIT | magic={this_magic}"
                f" already has {same_strategy_open} open position(s)"
                f" (max={PER_STRATEGY_MAX_OPEN_LIMITS.get(str(strategy or '').upper(), MAX_OPEN_PER_STRATEGY)})"
            )
            return {"retcode": -4, "comment": "PER_STRATEGY_MAX_OPEN_HIT"}

        blocked, same_direction_open = _check_symbol_direction_limit(
            mt5, symbol, signal, MAX_OPEN_PER_SYMBOL_DIRECTION
        )
        if blocked:
            print(
                f"🚫 SYMBOL_DIRECTION_LIMIT | {symbol} {signal}"
                f" already has {same_direction_open} open position(s)"
                f" (max={MAX_OPEN_PER_SYMBOL_DIRECTION})"
            )
            return {"retcode": -8, "comment": "SYMBOL_DIRECTION_MAX_OPEN_HIT"}

    except Exception as e:
        print(f"🛑 PER_STRATEGY CHECK FAILED (fail-closed): {e}")
        return {"retcode": -7, "comment": "PER_STRATEGY_CHECK_FAILED"}

    # =========================================
    # STEP 4: الحد اليومي الكلي = 50 صفقة
    # =========================================
    if _live_daily_cap_hit():
        print(
            f"🚫 DAILY_CAP_HIT | {_live_trade_count}/{MAX_LIVE_DAILY_TRADES}"
            f" trades executed today"
        )
        return {"retcode": -5, "comment": "GLOBAL_DAILY_CAP_HIT"}

    # ----- [SLTP-4]: single, authoritative SL/TP finalization — see
    # core/sl_tp_finalizer.py for why this replaced three independent
    # re-derivations of the same numbers (builder-vs-executor drift was
    # exactly how the earlier SL/TP bugs happened). -----
    from core.sl_tp_finalizer import finalize_sl_tp

    original_sl_dist = sl_dist
    original_tp_dist = tp_dist
    symbol = request.get('symbol', '')
    point = 0.01
    if MT5_AVAILABLE and mt5 is not None:
        try:
            sym_info = mt5.symbol_info(symbol)
            if sym_info:
                point = float(getattr(sym_info, 'point', 0.01) or 0.01)
        except Exception:
            pass

    price = float(request.get('price', 0) or 0)
    final = finalize_sl_tp(
        symbol=symbol,
        sl_dist_raw=sl_dist,
        tp_dist_raw=tp_dist,
        point=point,
        strategy=strategy,
        atr=atr,
        tp_tiers_raw=tp_tiers,
        entry_price=price if price > 0 else None,
        signal=signal,
        market_regime=market_regime,
        confidence=confidence,
    )
    if not final["valid"]:
        reason = final["stop_reason"] or "INVALID_SL_TP_CONSTRAINTS"
        print(f"🛑 ORDER_BLOCKED | {reason}")
        return {"retcode": -11, "comment": reason}
    sl_dist = final['sl_dist']
    tp_dist = final['tp_dist']
    tp_tiers = final['tp_tiers'] if final['tp_tiers'] is not None else tp_tiers

    if sl_dist != original_sl_dist:
        print(f'🛡 MIN STOP APPLIED | was={original_sl_dist} → now={sl_dist}')
    if tp_dist != original_tp_dist:
        print(f'🛡 TP_RATIO_FIXED | was_tp={original_tp_dist} → now_tp={tp_dist} | rr={final["rr"]}')

    # ----- Update SL/TP in request to match enforced values -----
    # FER3ON FINAL BUGFIX [SLTP-1]: sl_dist/tp_dist are RAW PRICE UNITS (e.g.
    # $29.35 for gold), not points — see _enforce_min_stop_distance's
    # docstring and FER3ON_FINAL_CHANGELOG.md [SLTP-1] for the full trace.
    # Previously multiplied by `point` here, which shrank a real ~$15-90
    # stop down to ~$0.15-0.90 whenever the (buggy) floor wasn't already
    # masking it. Used directly against `price` now, exactly like
    # core/trailing_stop.py already does with the same value.
    print(f'💵 SL/TP DISTANCE (raw price units) | sl_dist=${sl_dist:.2f} tp_dist=${tp_dist:.2f}')
    if price > 0:
        if str(request.get('type')).startswith('1'):  # SELL
            request['sl'] = round(price + sl_dist, 5)
            request['tp'] = round(price - tp_dist, 5)
        else:  # BUY
            request['sl'] = round(price - sl_dist, 5)
            request['tp'] = round(price + tp_dist, 5)

    # ----- FER3ON FINAL: send with progressive widening on stops-too-close
    # rejection (ported from V9FINAL1 — build spec Merge item #1 /
    # [EXEC-1]). Wraps the pre-existing filling-mode fallback loop — see
    # _send_order_with_stops_retry for full documentation of both retry
    # mechanisms.
    #
    # §3.3 Execution Quality Engine (analytics/execution_quality.py):
    # timestamp the request right before it is actually sent, so post-trade
    # delay tracking below measures real broker round-trip time, not any
    # of the risk/lot-adjustment work done above.
    _eq_requested_time = datetime.now(timezone.utc)
    _eq_requested_price = price
    _eq_symbol = symbol

    result, sl_dist, tp_dist = _send_order_with_stops_retry(
        request,
        symbol,
        point,
        sl_dist,
        tp_dist,
        price,
        signal,
        sl_cap=final["sl_cap"],
        decision_id=decision_id,
        strategy=_strat_key,
    )

    try:
        append_trade_event(
            "EXECUTION_RESULT",
            decision_id,
            symbol=symbol,
            strategy=_strat_key,
            retcode=getattr(result, "retcode", None),
            comment=getattr(result, "comment", None),
            order_ticket=getattr(result, "order", None),
            deal_ticket=getattr(result, "deal", None),
            fill_price=getattr(result, "price", None),
            fill_volume=getattr(result, "volume", None),
        )
    except OSError as ledger_error:
        _log_executor_exception(
            "TRADE_EVENT_LEDGER_RESULT_WRITE_FAILED",
            ledger_error,
            strategy=_strat_key,
            decision_id=decision_id,
        )
        print(f"🚨 TRADE_EVENT_LEDGER_RESULT_WRITE_FAILED: {ledger_error}")

    if result is None:
        print('❌ EXECUTION FAILED | no order result after all retries')
        return None

    print('📥 ORDER RESULT (final):')
    print(result)

    # Update request['sl']/['tp'] with the values actually sent (may be wider
    # than the original if a retry was needed) — keeps downstream logging
    # accurate. Same raw-price-unit fix as above.
    if price > 0:
        if str(request.get('type')).startswith('1'):  # SELL
            request['sl'] = round(price + sl_dist, 5)
            request['tp'] = round(price - tp_dist, 5)
        else:  # BUY
            request['sl'] = round(price - sl_dist, 5)
            request['tp'] = round(price + tp_dist, 5)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(
            f'❌ EXECUTION FAILED'
            f' | retcode={result.retcode}'
        )
        # §3.3 Execution Quality Engine — record the rejection. Pure
        # observability: wrapped so a logging failure can never turn a
        # rejection response into something that looks like a crash.
        try:
            from analytics.execution_quality import record_execution_outcome
            record_execution_outcome(
                ticket=getattr(result, 'order', None),
                requested_price=_eq_requested_price,
                filled_price=None,
                requested_time=_eq_requested_time,
                filled_time=None,
                rejected=True,
                symbol=_eq_symbol,
                strategy=strategy,
            )
            from core.error_memory import record_error_episode
            record_error_episode(category="EXECUTION_REJECTED", outcome="REJECTED", strategy=strategy)
        except Exception as _eq_err:
            _log_executor_exception('EXECUTION_QUALITY_REJECT_LOG_FAILED', _eq_err, strategy=_strat_key)
            print(f'⚠️ EXECUTION_QUALITY_LOG_FAILED (non-fatal): {_eq_err}')
        return result

    filled_lot = get_filled_volume(result, request.get("volume", lot))
    if filled_lot <= 0:
        print("❌ EXECUTION RESULT INVALID | successful order has no positive filled volume")
        return {"retcode": -9, "comment": "INVALID_FILLED_VOLUME"}
    requested_lot = float(request.get("volume", lot) or lot)
    if filled_lot != requested_lot:
        print(
            f"ℹ️ EXECUTION_VOLUME_CONFIRMED | requested={requested_lot:g}"
            f" filled={filled_lot:g}"
        )

    # تسجيل الصفقة في العداد اليومي بعد نجاح التنفيذ
    _register_live_trade()
    print(f"📊 DAILY_COUNTER | {_live_trade_count}/{MAX_LIVE_DAILY_TRADES} trades today")

    # identity محقونة مسبقاً في STEP 1 — نستخدم القيم مباشرة من request
    _strategy_id = str(strategy or "UNKNOWN")
    _magic_id = int(request.get("magic") or magic or 0)
    _raw_magic = magic or 0
    _magic_mismatch = False
    print(
        f'✅ TRADE EXECUTED'
        f' | ticket={result.order}'
        f' | lot={filled_lot}'
        f' | strategy={_strategy_id}'
        f' | magic={_magic_id}'
    )

    # §3.3 Execution Quality Engine — record the fill (slippage/delay).
    # Pure observability, never affects the trade already confirmed above.
    try:
        from analytics.execution_quality import record_execution_outcome
        record_execution_outcome(
            ticket=result.order,
            requested_price=_eq_requested_price,
            filled_price=getattr(result, 'price', None),
            requested_time=_eq_requested_time,
            filled_time=datetime.now(timezone.utc),
            rejected=False,
            symbol=_eq_symbol,
            strategy=strategy,
        )
    except Exception as _eq_err:
        _log_executor_exception('EXECUTION_QUALITY_FILL_LOG_FAILED', _eq_err, strategy=_strat_key)
        print(f'⚠️ EXECUTION_QUALITY_LOG_FAILED (non-fatal): {_eq_err}')

    try:
        persist_trade_log(
            trade_number=result.order,
            signal=signal,
            lot=filled_lot,
            profit=0,
            result='OPEN',
            strategy=_strategy_id,
            sl_dist=sl_dist,
            tp_dist=tp_dist,
            rr_ratio=rr_ratio,
            risk_percent=risk_percent,
            exec_grade=exec_grade,
            brain_score=final_brain['final_score'],
            quality_score=quality_score,
            confidence_pct=confidence.get('pct', 0),
            market_regime=market_regime,
            atr=atr,
            session=session,
            magic=_magic_id,
            raw_magic=_raw_magic,
            magic_mismatch=_magic_mismatch,
            build_id=BUILD_ID,
            decision_id=decision_id,
            entry_price=request.get("price"),
            stop_price=request.get("sl"),
            target_price=request.get("tp"),
            stop_source=(stop_diagnostics or {}).get("selected_stop_source"),
            stop_anchor_price=(stop_diagnostics or {}).get("selected_swing"),
            stop_anchor_index=(
                (stop_diagnostics or {}).get("selected_stop_anchor") or {}
            ).get("index"),
            stop_anchor_label=(
                (stop_diagnostics or {}).get("selected_stop_anchor") or {}
            ).get("label"),
            stop_reason=(stop_diagnostics or {}).get("stop_selection_reason"),
            stop_buffer=(stop_diagnostics or {}).get("structure_buffer"),
            entry_reason=entry_reason or "",
            entry_conditions=json.dumps(
                entry_conditions or [], ensure_ascii=False, default=str
            ),
        )
    except Exception as e:
        _log_executor_exception('TRADE_LOG_PERSIST_FAILED', e, strategy=_strat_key)
        print(f'⚠️ LOGGING FAILED: {e}')

    try:
        _raw_magic_val = _raw_magic
        _mm_val = _magic_mismatch
        # ENRICHMENT FIX: choch/liquidity/mtf fields were computed upstream
        # (main.py's SMC snapshot and structure analysis)
        # for ML feature extraction but were never threaded through to the
        # memory record itself, so ai_memory.csv's choch_strength,
        # liq_map_score, liq_map_dir and mtf_structural columns stayed
        # empty for every trade regardless of how much real analysis had
        # actually been done. These are now optional kwargs on
        # execute_trade() (default None) — only written when a caller
        # actually supplies them, so callers that don't compute this yet
        # keep prior behavior (empty, not a fabricated placeholder).
        _enrichment_kwargs = {}
        if choch_state is not None:
            _enrichment_kwargs['choch_state'] = choch_state
        if choch_strength is not None:
            _enrichment_kwargs['choch_strength'] = choch_strength
        if liq_map_score is not None:
            _enrichment_kwargs['liq_map_score'] = liq_map_score
        if liq_map_dir is not None:
            _enrichment_kwargs['liq_map_dir'] = liq_map_dir
        if mtf_strength is not None:
            _enrichment_kwargs['mtf_strength'] = mtf_strength
        if mtf_structural is not None:
            _enrichment_kwargs['mtf_structural'] = mtf_structural

        save_trade_memory(
            ticket=result.order,
            strategy=_strategy_id,
            signal=signal,
            result='OPEN',
            profit=0,
            atr=atr,
            market_regime=market_regime,
            hour=datetime.now(timezone.utc).hour,
            spread=0,
            session=session,
            quality_score=quality_score,
            confidence_score=confidence.get('pct', 0),
            confidence_pct=confidence.get('pct', 0),
            exec_grade=exec_grade,
            rr_ratio=rr_ratio,
            sl_dist=sl_dist,
            tp_dist=tp_dist,
            tp_tiers=json.dumps(tp_tiers, ensure_ascii=False) if tp_tiers is not None else None,
            magic=_magic_id,
            volume=filled_lot,
            brain_score=final_brain.get('final_score', 0),
            decision_reason=entry_reason or 'OPEN_EXECUTION_CAPTURE',
            decision_id=decision_id,
            entry_reason=entry_reason or "",
            entry_conditions=json.dumps(
                entry_conditions or [], ensure_ascii=False, default=str
            ),
            stop_source=(stop_diagnostics or {}).get("selected_stop_source"),
            stop_anchor_price=(stop_diagnostics or {}).get("selected_swing"),
            stop_anchor_index=(
                (stop_diagnostics or {}).get("selected_stop_anchor") or {}
            ).get("index"),
            stop_anchor_label=(
                (stop_diagnostics or {}).get("selected_stop_anchor") or {}
            ).get("label"),
            stop_reason=(stop_diagnostics or {}).get("stop_selection_reason"),
            stop_buffer=(stop_diagnostics or {}).get("structure_buffer"),
            conflict_report=(
                f'RAW_MAGIC={_raw_magic_val}'
                if _mm_val else ''
            ),
            **_enrichment_kwargs,
        )
    except Exception as e:
        _log_executor_exception('TRADE_MEMORY_SAVE_FAILED', e, strategy=_strat_key)
        print(f'⚠️ MEMORY SAVE FAILED: {e}')

    try:
        register_test_mode_trade(lot=filled_lot)
    except Exception as e:
        _log_executor_exception('TEST_MODE_QUOTA_UPDATE_FAILED', e, strategy=_strat_key)
        print(f'⚠️ TEST MODE QUOTA UPDATE FAILED: {e}')

    # =========================================
    # V3.6: MULTI-TP LADDER — حساب جدول TP1/TP2/TP3 (أو SINGLE_FAST_EXIT
    # عند تعارض MTF) لاستخدامه من المُراقب الدوري للصفقات المفتوحة.
    # حسابي فقط هنا — التنفيذ الفعلي (partial close) يتم في حلقة المراقبة.
    # =========================================
    try:
        from execution.multi_tp import compute_tp_prices, register_tp_ladder
        _entry_price = float(request.get('price', 0) or 0)
        _direction = 'BUY' if str(request.get('type')).startswith('0') else 'SELL'
        tp_ladder = compute_tp_prices(
            entry_price=_entry_price,
            sl_distance=sl_dist,
            direction=_direction,
            strategy=_strategy_id,
            mtf_mode=mtf_alignment_mode,
            point=point,
            max_tp_distance=tp_dist,
        )
        if tp_ladder.get("enabled"):
            register_tp_ladder(result.order, {**tp_ladder, 'base_volume': filled_lot})
        print(
            f"🎯 MULTI_TP_LADDER | strategy={_strategy_id}"
            f" | mode={tp_ladder.get('mode')}"
            f" | levels={tp_ladder.get('levels')}"
        )
    except Exception as e:
        _log_executor_exception('TP_LADDER_COMPUTE_FAILED', e, strategy=_strat_key)
        print(f'⚠️ MULTI_TP_LADDER COMPUTE FAILED: {e}')
        tp_ladder = {"enabled": False, "levels": [], "mode": "ERROR"}

    return result