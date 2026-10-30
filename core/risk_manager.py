# =========================================
# FER3ON V3-FIXED — UNIFIED AI RISK ENGINE
# Smart Aggression + Adaptive Cooldown
# + Session Intelligence + Recovery AI
# مُعدّل لحساب 1000$ + 80 صفقة يومياً
# =========================================

import time
from datetime import datetime, timezone
from core.mt5_compat import mt5, MT5_AVAILABLE

from core.settings import (
    MAX_RISK_TOTAL,
    MAX_LOT,
    MIN_LOT,
    MIN_SL_DISTANCE,
    MAX_SL_DISTANCE_DOLLARS,
    TOTAL_RISK_CAP,
    MIN_LOT_RISK_MULTIPLE_CAP,
    QUALITY_RISK_TABLE,
    TESTING_MODE,
    TESTING_MODE_LOT_CAPS,
    V7_PLUS_ENABLED,
    MAX_DAILY_LOSS_USD,
    BASE_ACCOUNT_BALANCE,
    SYMBOL,
    MAX_OPEN_TRADES,
    PER_STRATEGY_SOFT_POSITION_LIMITS,
)
from core.test_mode_manager import can_allocate as test_mode_can_allocate, planned_lot_for_mode
from core.daily_loss_guard import get_daily_loss_status as _get_daily_loss_status


def compute_realized_risk_percent(*, lot: float, entry_price: float, sl_price: float,
                                   balance: float, symbol: str = SYMBOL) -> float:
    """FER3ON FINAL [EXPOSURE-1]: the actual %-of-balance risk a trade carries,
    computed from the FINAL lot and SL price actually sent to the broker —
    not the nominal pre-sizing risk_percent request.

    Why this exists: core.portfolio_risk_authority.compute_current_exposure()
    sums the `risk_percent` field recorded per open trade to enforce
    MAX_RISK_TOTAL. Before this fix, callers recorded the *nominal* requested
    risk_percent (e.g. main.py's `risk_percent = round(max(0.10, min(0.75,
    0.50 * risk_multiplier)), 3)` — a small 0.10-0.75% figure). But
    core.risk_manager.calculate_smart_lot's MIN_LOT_RISK_GUARD ([SLTP-2])
    means the REAL dollar risk on a $200-$1000 account is often ~1-5% per
    trade (MIN_LOT dominates the sizing, not the nominal risk_percent). The
    portfolio-wide exposure cap was therefore checking aggregate exposure
    against numbers ~5-10x smaller than reality, and could never actually
    trigger before real aggregate risk got dangerous. This function closes
    that gap by recording what was ACTUALLY risked, not what was asked for.
    """
    try:
        if lot <= 0 or balance <= 0 or entry_price <= 0 or sl_price <= 0:
            return 0.0
        point = 0.01
        tick_value = 1.0
        if MT5_AVAILABLE and mt5 is not None:
            info = mt5.symbol_info(symbol)
            if info is not None:
                point = float(getattr(info, 'point', 0.01) or 0.01)
                tv = float(getattr(info, 'trade_tick_value', 0.0) or 0.0)
                if tv > 0:
                    tick_value = tv
        sl_price_dist = abs(float(entry_price) - float(sl_price))
        sl_points = sl_price_dist / point if point > 0 else sl_price_dist
        risk_dollars = float(lot) * sl_points * tick_value
        return round((risk_dollars / float(balance)) * 100.0, 4)
    except Exception as e:
        print(f'⚠️ REALIZED_RISK_COMPUTE_FAILED (non-fatal): {e}')
        return 0.0

# =========================================
# SESSION MULTIPLIERS
# =========================================

SESSION_LOT_MULT = {
    'LONDON': 1.00,
    'NEWYORK': 1.00,
    'OVERLAP': 1.10,
    'ASIA': 0.70,
    'OFF_HOURS': 0.50,
}

# =========================================
# AI AGGRESSION PROFILES
# =========================================

AGGRESSION_PROFILES = {
    'SAFE': {
        'lot_mult': 0.70,
        'threshold_bonus': +6,
        'max_risk': 0.70,
    },
    'SMART': {
        'lot_mult': 0.85,
        'threshold_bonus': 0,
        'max_risk': 0.85,
    },
    'AGGRESSIVE': {
        'lot_mult': 0.95,
        'threshold_bonus': -4,
        'max_risk': 1.00,
    },
    'CONTROLLED_AGGRESSION': {
        'lot_mult': 1.00,
        'threshold_bonus': -6,
        'max_risk': 1.00,
    },
}

# =========================================
# RECOVERY MEMORY
# =========================================

_last_loss_time = 0
_consecutive_losses = 0
_daily_loss_total = 0.0
_weekly_loss_total = 0.0

# =========================================
# HELPERS
# =========================================

def _now():
    return time.time()


def _normalize_strategy(strategy):
    return str(strategy or 'SMC').upper()


def _clamp(v, low, high):
    return max(low, min(high, v))


# =========================================
# POSITION MANAGER (single gate for open-position policy)
# =========================================

class PositionManager:
    """Single object that enforces the open-position policy for all strategies."""

    def evaluate(self, *, strategy='SMC', current_positions=0, total_positions=0):
        result = evaluate_position_limits(
            strategy=strategy,
            current_positions=current_positions,
            total_positions=total_positions,
        )
        if not result['allowed']:
            result['reason'] = f"{result['reason']}|POSITION_LIMIT"
        return result

    def can_open(self, *, strategy='SMC', current_positions=0, total_positions=0):
        result = self.evaluate(
            strategy=strategy,
            current_positions=current_positions,
            total_positions=total_positions,
        )
        return bool(result['allowed']), result


_position_manager = None


def get_position_manager() -> PositionManager:
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager


# =========================================
# SMART COOLDOWN SYSTEM
# =========================================

def register_loss(pnl=0.0):
    global _last_loss_time
    global _consecutive_losses
    global _daily_loss_total
    global _weekly_loss_total

    _last_loss_time = _now()
    _consecutive_losses += 1
    _daily_loss_total += abs(float(pnl) or 0.0)
    _weekly_loss_total += abs(float(pnl) or 0.0)

    print(
        f'[AI-RISK] LOSS_REGISTERED'
        f' | losses={_consecutive_losses}'
    )


def register_win(pnl=0.0):
    global _consecutive_losses

    if _consecutive_losses > 0:
        _consecutive_losses -= 1

    print(
        f'[AI-RISK] WIN_REGISTERED'
        f' | losses={_consecutive_losses}'
    )


def get_cooldown_minutes():
    if _consecutive_losses <= 0:
        return 0

    if _consecutive_losses == 1:
        return 10

    if _consecutive_losses == 2:
        return 20

    if _consecutive_losses == 3:
        return 35

    return 60


def get_loss_limits_status(balance=None) -> dict:
    """
    Read broker-confirmed daily PnL and expose the fixed USD threshold plus
    percentage equivalents for legacy sizing callers.
    """
    try:
        daily_status = _get_daily_loss_status(symbol=SYMBOL)
        daily_loss_usd = float(daily_status["daily_loss"])
        pnl_source = "mt5_live_sync"
    except Exception as exc:
        print(f'[risk_manager] MT5 daily loss unavailable: {exc}')
        daily_loss_usd = MAX_DAILY_LOSS_USD
        pnl_source = "unavailable_fail_closed"

    account_balance = max(float(balance or BASE_ACCOUNT_BALANCE), 1.0)
    daily_used_pct = daily_loss_usd / account_balance * 100.0
    daily_limit_pct = MAX_DAILY_LOSS_USD / account_balance * 100.0

    weekly_used_pct = daily_used_pct * 3.0
    weekly_limit_pct = daily_limit_pct * 4.0
    return {
        'daily_used': round(daily_used_pct, 3),
        'weekly_used': round(weekly_used_pct, 3),
        'daily_limit': daily_limit_pct,
        'weekly_limit': weekly_limit_pct,
        'daily_loss_usd': round(daily_loss_usd, 2),
        'daily_loss_limit_usd': MAX_DAILY_LOSS_USD,
        'daily_remaining': max(0.0, round(daily_limit_pct - daily_used_pct, 3)),
        'weekly_remaining': max(0.0, round(weekly_limit_pct - weekly_used_pct, 3)),
        'consecutive_losses': _consecutive_losses,
        'source': pnl_source,
    }


def evaluate_position_limits(*, strategy='SMC', current_positions=0, total_positions=0):
    strategy_key = str(strategy or 'SMC').upper()
    # V3.5 PHASE-1 FIX: 'TOTAL' previously hardcoded to 80, contradicting
    # settings.MAX_OPEN_TRADES=4 — this was a second, independent source of
    # the unbounded-concurrent-trades bug. Now reads the single source of
    # truth. [REARCH-2]: the per-strategy numbers used to be a second
    # hardcoded dict living only here; they now live in settings.py's
    # PER_STRATEGY_SOFT_POSITION_LIMITS alongside MAX_OPEN_TRADES itself, so
    # this file has exactly one place it reads position-count policy from.
    limits = dict(PER_STRATEGY_SOFT_POSITION_LIMITS)
    limits['TOTAL'] = MAX_OPEN_TRADES
    current = int(current_positions or 0)
    total = int(total_positions or 0)
    allowed = True
    reason = 'POSITION_LIMIT_OK'

    if strategy_key in limits and current >= limits[strategy_key]:
        allowed = False
        reason = f'{strategy_key}_POSITION_LIMIT_REACHED'
    elif total >= limits['TOTAL']:
        allowed = False
        reason = f'{strategy_key}_TOTAL_POSITION_LIMIT_REACHED'

    return {
        'allowed': allowed,
        'reason': reason,
        'strategy': strategy_key,
        'current_positions': current,
        'total_positions': total,
        'hard_limits': limits,
    }


def cooldown_active():
    if _last_loss_time <= 0:
        return False

    cooldown = get_cooldown_minutes() * 60
    remaining = cooldown - (_now() - _last_loss_time)

    if remaining > 0:
        mins = round(remaining / 60, 1)

        print(
            f'[AI-RISK] COOLDOWN_ACTIVE'
            f' | remaining={mins}m'
            f' | losses={_consecutive_losses}'
        )

        return True

    return False


# =========================================
# QUALITY RISK
# =========================================

def get_quality_risk(quality_score):

    for threshold, risk in QUALITY_RISK_TABLE:
        if quality_score >= threshold:
            return min(risk, MAX_RISK_TOTAL)

    return min(
        QUALITY_RISK_TABLE[-1][1],
        MAX_RISK_TOTAL
    )


# =========================================
# AI RISK ADAPTATION
# =========================================

def compute_ai_risk_modifier(
    ai_score=50,
    brain_score=50,
    session_score=50,
    aggression_mode='SMART',
    strategy='SMC',
):
    profile = AGGRESSION_PROFILES.get(
        str(aggression_mode).upper(),
        AGGRESSION_PROFILES['SMART']
    )

    score = (
        float(ai_score) * 0.40 +
        float(brain_score) * 0.35 +
        float(session_score) * 0.25
    )

    modifier = 1.0

    if score >= 90:
        modifier *= 1.25

    elif score >= 80:
        modifier *= 1.15

    elif score >= 70:
        modifier *= 1.05

    elif score < 55:
        modifier *= 0.75

    modifier *= float(profile['lot_mult'])

    strategy = _normalize_strategy(strategy)

    if strategy == 'RECOVERY':
        modifier *= 0.70

    modifier = _clamp(
        modifier,
        0.30,
        float(profile['max_risk'])
    )

    return round(modifier, 2)


# =========================================
# SMART LOT CALCULATION — مُعدّل للـ 1000$
# =========================================

def calculate_smart_lot(
    balance,
    risk_percent,
    sl_dist,
    symbol='XAUUSD',
    quality_score=70,
    session='UNKNOWN',
    recovery_mode=False,
    exec_grade='A',
    ai_score=50,
    brain_score=50,
    session_score=50,
    aggression_mode='SMART',
    strategy='SMC',
    market_regime='UNKNOWN',
    max_daily_loss=None,
    max_weekly_loss=None,
    size_mode=None,
):
    if cooldown_active():
        return 0.0, 0.0, ['COOLDOWN_ACTIVE']

    if sl_dist <= 0 or balance <= 0:
        return 0.0, 0.0, ['ERROR:invalid_inputs']

    risk_percent = min(
        float(risk_percent),
        MAX_RISK_TOTAL
    )

    risk_amount = balance * (risk_percent / 100)
    loss_limits = get_loss_limits_status(balance=balance)
    daily_limit = float(max_daily_loss if max_daily_loss is not None else loss_limits['daily_limit'])
    weekly_limit = float(max_weekly_loss if max_weekly_loss is not None else loss_limits['weekly_limit'])

    if loss_limits['daily_used'] >= daily_limit or loss_limits['weekly_used'] >= weekly_limit:
        return 0.0, 0.0, ['RISK_LIMITS_HIT']

    sym_info = mt5.symbol_info(symbol)

    if sym_info and sym_info.trade_tick_value > 0:
        tick_value = sym_info.trade_tick_value
        lot_step = sym_info.volume_step or 0.01
        point = float(getattr(sym_info, 'point', 0.01) or 0.01)

    else:
        tick_value = 0.10
        lot_step = 0.01
        point = 0.01

    # FER3ON FINAL BUGFIX [SLTP-1]: sl_dist is in RAW PRICE UNITS (e.g.
    # $29.35 for gold — see core/trade_executor.py::_enforce_min_stop_distance
    # and FER3ON_FINAL_CHANGELOG.md [SLTP-1]), but MT5's tick_value convention
    # is "$ per point per 1.0 lot", so the lot-sizing formula below needs the
    # stop distance in POINTS, not raw price dollars. Previously `sl` was
    # used directly (raw price ~$15-90) in `risk_amount / (sl * tick_value)`,
    # which is dimensionally wrong by a factor of ~1/point (~100x for gold)
    # and would have produced a lot size ~100x too large once [SLTP-1]'s
    # other fix let the real adaptive sl_dist through instead of the old
    # (also buggy) flat-1500 override that accidentally masked this.
    sl_price_dist = max(float(sl_dist), float(MIN_SL_DISTANCE) * point)
    # FER3ON FINAL [SLTP-2]: cap the stop for this account size — see
    # settings.py MAX_SL_DISTANCE_DOLLARS. Keeps the risk this function
    # computes consistent with what trade_executor.py will actually send.
    sl_price_dist = min(sl_price_dist, MAX_SL_DISTANCE_DOLLARS)
    sl_points = sl_price_dist / point if point > 0 else sl_price_dist

    raw_lot = (
        risk_amount / (sl_points * tick_value)
        if tick_value > 0
        else MIN_LOT
    )

    lot = raw_lot

    adjustments = []

    # =====================================
    # QUALITY SCORE
    # =====================================

    if quality_score >= 95:
        lot *= 1.20
        adjustments.append('Q95+:×1.20')

    elif quality_score >= 90:
        lot *= 1.10
        adjustments.append('Q90+:×1.10')

    elif quality_score >= 80:
        lot *= 1.00
        adjustments.append('Q80+:×1.00')

    elif quality_score < 60:
        lot *= 0.70
        adjustments.append('Q<60:×0.70')

    # =====================================
    # SESSION MULTIPLIER
    # =====================================

    sm = SESSION_LOT_MULT.get(session, 1.0)

    if sm != 1.0:
        lot *= sm
        adjustments.append(f'Sess({session}):×{sm}')

    # =====================================
    # RECOVERY MODE
    # =====================================

    if recovery_mode:
        lot *= 0.50
        adjustments.append('Recovery:×0.50')

    regime_mult = {
        'TRENDING': 1.00,
        'RANGING': 0.90,
        'VOLATILE': 0.70,
        'CRISIS': 0.50,
        'UNKNOWN': 0.85,
    }.get(str(market_regime).upper(), 0.85)
    lot *= regime_mult
    adjustments.append(f'Regime({market_regime}):×{regime_mult}')

    # =====================================
    # EXECUTION GRADE
    # =====================================

    grade_mult = {
        'ELITE': 1.20,
        'A+': 1.12,
        'A': 1.00,
        'B+': 0.92,
        'B': 0.84,
        'C': 0.70,
    }.get(exec_grade, 1.0)

    if grade_mult != 1.0:
        lot *= grade_mult
        adjustments.append(f'Exec({exec_grade}):×{grade_mult}')

    # =====================================
    # AI AGGRESSION
    # =====================================

    ai_modifier = compute_ai_risk_modifier(
        ai_score=ai_score,
        brain_score=brain_score,
        session_score=session_score,
        aggression_mode=aggression_mode,
        strategy=strategy,
    )

    lot *= ai_modifier

    adjustments.append(
        f'AI({aggression_mode}):×{ai_modifier}'
    )

    # =====================================
    # LOSS ADAPTATION
    # =====================================

    if _consecutive_losses >= 2:
        reduction = max(
            0.45,
            1.0 - (_consecutive_losses * 0.10)
        )

        lot *= reduction

        adjustments.append(
            f'LossAdapt:×{round(reduction,2)}'
        )

    # =====================================
    # ROUNDING
    # =====================================

    lot = round(
        round(lot / lot_step) * lot_step,
        2
    )

    daily_loss_remaining = max(
        0.0,
        float(
            loss_limits.get(
                'daily_loss_limit_usd',
                daily_limit * float(balance) / 100.0,
            )
        )
        - float(
            loss_limits.get(
                'daily_loss_usd',
                float(loss_limits['daily_used']) * float(balance) / 100.0,
            )
        ),
    )
    risk_per_lot = sl_points * tick_value
    max_daily_lot = (
        int((daily_loss_remaining / risk_per_lot + 1e-9) / lot_step) * lot_step
        if risk_per_lot > 0 and lot_step > 0 else 0.0
    )
    max_daily_lot = round(max_daily_lot, 8)
    if max_daily_lot < MIN_LOT:
        adjustments.append(
            f'DAILY_LOSS_BUDGET_EXHAUSTED:remaining=${daily_loss_remaining:.2f}'
        )
        return 0.0, round(raw_lot, 4), adjustments
    if lot > max_daily_lot:
        lot = max_daily_lot
        adjustments.append(
            f'DAILY_LOSS_BUDGET_CAP:lot={max_daily_lot:.3f}'
        )

    # FIXED: lot caps من TESTING_MODE_LOT_CAPS للـ 1000$
    if TESTING_MODE:
        cap = TESTING_MODE_LOT_CAPS.get(str(size_mode or 'NORMAL').upper(), 0.20)
        lot = min(lot, cap)
        quota = test_mode_can_allocate(lot=lot, size_mode=size_mode)
        if not quota['allowed']:
            return 0.0, round(raw_lot, 2), adjustments + [quota['reason']]
        lot = min(float(quota['planned_lot']), max_daily_lot)
        adjustments.append(f"TestMode:{quota['bucket']}|lot={lot:.3f}")
    else:
        # Conservatively cap lot size for small real accounts and keep demo mode safe.
        if float(balance or 0.0) <= 100.0:
            max_lot = min(MAX_LOT, 0.01)
        else:
            max_lot = MAX_LOT

        lot = max(MIN_LOT, min(lot, max_lot, max_daily_lot))

        # =====================================
        # FER3ON FINAL — MIN-LOT RISK GUARD [SLTP-2]
        # `lot` was just floored to MIN_LOT if the risk-based raw_lot rounded
        # below it. On a small account with a wide gold stop, MIN_LOT can
        # imply MUCH more dollar risk than risk_percent intended (e.g. 0.01
        # lot × $30 stop = $30 = 15% of a $200 balance vs an intended 0.75%).
        # Rather than silently open that oversized trade, check the risk
        # MIN_LOT actually implies against what was intended; skip the trade
        # (lot=0.0, respected by every caller via the existing `if lot > 0`
        # convention) if it's too far over budget.
        # =====================================
        if lot <= MIN_LOT + 1e-9:
            implied_risk = lot * sl_points * tick_value
            risk_cap = risk_amount * MIN_LOT_RISK_MULTIPLE_CAP
            if risk_amount > 0 and implied_risk > risk_cap:
                adjustments.append(
                    f'MIN_LOT_RISK_GUARD:skip '
                    f'(min_lot_risk=${implied_risk:.2f} > '
                    f'{MIN_LOT_RISK_MULTIPLE_CAP}x intended=${risk_amount:.2f})'
                )
                print(
                    f'🛑 MIN_LOT_RISK_GUARD | balance=${balance:.0f} sl=${sl_price_dist:.2f} '
                    f'| MIN_LOT implies ${implied_risk:.2f} risk vs intended ${risk_amount:.2f} '
                    f'({MIN_LOT_RISK_MULTIPLE_CAP}x cap) | SKIPPING TRADE'
                )
                return 0.0, round(raw_lot, 4), adjustments

        implied_risk = lot * sl_points * tick_value
        if implied_risk > TOTAL_RISK_CAP + 1e-9:
            cap_factor = (TOTAL_RISK_CAP / (sl_points * tick_value)) if (sl_points * tick_value) > 0 else MIN_LOT
            capped_lot = max(
                MIN_LOT,
                min(float(cap_factor), max_lot, max_daily_lot),
            )
            capped_lot = (
                int((capped_lot + 1e-9) / lot_step) * lot_step
                if lot_step > 0 else 0.0
            )
            capped_lot = round(min(capped_lot, max_daily_lot), 2)
            if capped_lot < MIN_LOT:
                adjustments.append(
                    f'DAILY_LOSS_BUDGET_EXHAUSTED:remaining=${daily_loss_remaining:.2f}'
                )
                return 0.0, round(raw_lot, 4), adjustments
            adjustments.append(
                f'TOTAL_RISK_CAP:cap lot={capped_lot:.2f} '
                f'(implied_risk=${implied_risk:.2f} > cap=${TOTAL_RISK_CAP:.2f})'
            )
            print(
                f'🛑 TOTAL_RISK_CAP | balance=${balance:.0f} sl=${sl_price_dist:.2f} '
                f'| implied_risk=${implied_risk:.2f} > cap=${TOTAL_RISK_CAP:.2f} '
                f'| capping lot to {capped_lot:.2f}'
            )
            return capped_lot, round(raw_lot, 4), adjustments

    print(
        f'[AI-RISK]'
        f' mode={aggression_mode}'
        f' | strategy={strategy}'
        f' | ai_mod={ai_modifier}'
        f' | losses={_consecutive_losses}'
        f' | final_lot={lot:.3f}'
        f' | balance=${balance:.0f}'
    )

    return (
        lot,
        round(raw_lot, 2),
        adjustments
    )


# =========================================
# DYNAMIC RISK ENGINE
# =========================================

def calculate_dynamic_risk(
    strategy,
    master_score,
    session_score,
    dna_score,
    crisis_multiplier,
    market_regime,
):
    from core.settings import (
        BASE_RISK_DAILY,
        BASE_RISK_SMC,
    )

    if cooldown_active():
        return _block('COOLDOWN_ACTIVE')

    if master_score < 35:
        return _block('LOW_MASTER_SCORE')

    if session_score < 30:
        return _block('BAD_SESSION')

    if dna_score < 30:
        return _block('LOW_DNA_SCORE')

    if crisis_multiplier == 0:
        return _block('CRISIS_FREEZE')

    base = {
        'DAILY': BASE_RISK_DAILY,
        'SMC': BASE_RISK_SMC,
        'RECOVERY': BASE_RISK_SMC * 0.50,
    }.get(strategy, BASE_RISK_SMC)

    regime_mult = {
        'TRENDING': 1.00,
        'RANGING': 0.80,
        'VOLATILE': 0.50,
        'CRISIS': 0.30,
        'UNKNOWN': 0.70,
    }.get(market_regime, 0.80)

    risk = (
        base *
        regime_mult *
        crisis_multiplier
    )

    if _consecutive_losses >= 2:
        risk *= 0.70

    return {
        'allow_trade': True,
        'risk_percent': round(
            min(risk, MAX_RISK_TOTAL),
            3
        ),
        'reason': 'OK',
    }


# =========================================
# UNIFIED RISK ENGINE HELPERS
# =========================================


def get_session_risk_multiplier(session='UNKNOWN'):
    return float(SESSION_LOT_MULT.get(str(session or 'UNKNOWN').upper(), 1.0))


def get_risk_state():
    return {
        'last_loss_time': _last_loss_time,
        'consecutive_losses': _consecutive_losses,
        'daily_loss_total': round(_daily_loss_total, 2),
        'weekly_loss_total': round(_weekly_loss_total, 2),
        'cooldown_minutes': get_cooldown_minutes(),
    }


def record_trade_result(pnl=0.0):
    value = float(pnl or 0.0)
    if value < 0:
        register_loss(value)
        try:
            from risk.hard_risk_cap import record_trade_loss
            record_trade_loss(value)
        except Exception:
            pass
    else:
        register_win(value)
    return get_risk_state()


def check_drawdown_limits(balance=0.0, daily_limit=None, weekly_limit=None):
    limits = get_loss_limits_status(balance=balance)
    resolved_daily = float(daily_limit if daily_limit is not None else limits['daily_limit'])
    resolved_weekly = float(weekly_limit if weekly_limit is not None else limits['weekly_limit'])
    allowed = limits['daily_used'] < resolved_daily and limits['weekly_used'] < resolved_weekly
    reason = 'OK' if allowed else 'DRAWDOWN_LIMIT_REACHED'
    return {
        'allowed': allowed,
        'reason': reason,
        'daily_used': limits['daily_used'],
        'daily_limit': round(resolved_daily, 2),
        'weekly_used': limits['weekly_used'],
        'weekly_limit': round(resolved_weekly, 2),
        'consecutive_losses': limits['consecutive_losses'],
    }


def evaluate_unified_risk(
    *,
    balance,
    strategy='SMC',
    requested_risk_percent=0.0,
    sl_dist=0.0,
    symbol='XAUUSD',
    quality_score=70,
    session='UNKNOWN',
    recovery_mode=False,
    exec_grade='A',
    ai_score=50,
    brain_score=50,
    session_score=50,
    aggression_mode='SMART',
    market_regime='UNKNOWN',
    current_positions=0,
    total_positions=0,
):
    position_status = evaluate_position_limits(
        strategy=strategy,
        current_positions=current_positions,
        total_positions=total_positions,
    )
    if not position_status['allowed']:
        return {
            'allowed': False,
            'reason': position_status['reason'],
            'position_status': position_status,
            'drawdown_status': check_drawdown_limits(balance=balance),
            'cooldown_active': cooldown_active(),
        }

    drawdown_status = check_drawdown_limits(balance=balance)
    if not drawdown_status['allowed']:
        return {
            'allowed': False,
            'reason': drawdown_status['reason'],
            'position_status': position_status,
            'drawdown_status': drawdown_status,
            'cooldown_active': cooldown_active(),
        }

    try:
        from risk.hard_risk_cap import check_hard_risk_cap
        hard_risk = check_hard_risk_cap(
            balance,
            requested_risk_percent,
            drawdown_status.get('daily_loss_usd'),
        )
    except Exception as exc:
        hard_risk = {
            'enabled': False,
            'allowed': False,
            'hard_risk_status': 'ERROR',
            'capped_risk_percent': 0.0,
            'reason': f'HARD_RISK_CHECK_FAILED:{type(exc).__name__}',
        }

    if not hard_risk.get('allowed', True):
        return {
            'allowed': False,
            'reason': hard_risk.get('reason', 'HARD_RISK_BLOCK'),
            'position_status': position_status,
            'drawdown_status': drawdown_status,
            'hard_risk': hard_risk,
            'cooldown_active': cooldown_active(),
        }

    capped_risk = float(hard_risk.get('capped_risk_percent', requested_risk_percent) or 0.0)
    lot, raw_lot, adjustments = calculate_smart_lot(
        balance=balance,
        risk_percent=capped_risk,
        sl_dist=sl_dist,
        symbol=symbol,
        quality_score=quality_score,
        session=session,
        recovery_mode=recovery_mode,
        exec_grade=exec_grade,
        ai_score=ai_score,
        brain_score=brain_score,
        session_score=session_score,
        aggression_mode=aggression_mode,
        strategy=strategy,
        market_regime=market_regime,
        max_daily_loss=drawdown_status['daily_limit'],
        max_weekly_loss=drawdown_status['weekly_limit'],
    )
    return {
        'allowed': lot > 0,
        'reason': 'OK' if lot > 0 else 'LOT_BLOCKED',
        'requested_risk_percent': float(requested_risk_percent or 0.0),
        'capped_risk_percent': capped_risk,
        'lot': lot,
        'raw_lot': raw_lot,
        'adjustments': adjustments,
        'position_status': position_status,
        'drawdown_status': drawdown_status,
        'hard_risk': hard_risk,
        'session_risk_multiplier': get_session_risk_multiplier(session),
        'ai_risk_modifier': compute_ai_risk_modifier(
            ai_score=ai_score,
            brain_score=brain_score,
            session_score=session_score,
            aggression_mode=aggression_mode,
            strategy=strategy,
        ),
        'cooldown_active': cooldown_active(),
    }


# =========================================
# BACKWARD COMPAT
# =========================================

def calculate_lot_size(
    balance,
    risk_percent,
    stop_loss_distance,
    symbol='XAUUSD',
):
    lot, _, _ = calculate_smart_lot(
        balance,
        risk_percent,
        stop_loss_distance,
        symbol,
    )

    return lot


# =========================================
# BLOCK HELPER
# =========================================

def _block(reason):
    return {
        'allow_trade': False,
        'risk_percent': 0,
        'reason': reason,
    }