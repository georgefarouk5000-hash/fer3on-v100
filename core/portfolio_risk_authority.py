# =============================================================================
# FER3ON AI V3.5 — PORTFOLIO RISK AUTHORITY
# =============================================================================
# Phase-1 Stabilization: Authority becomes "Portfolio Risk Authority" ONLY.
#
# What Authority DOES (allowed):
#   - Risk Control
#   - Lot Allocation
#   - Exposure Management
#   - Portfolio Limits (per-strategy + total)
#   - Daily Loss Protection
#   - Drawdown Protection
#
# What Authority CANNOT do (forbidden):
#   - Decide direction (BUY/SELL) — that's strategy + unified_decision
#   - Reject a trade solely because another strategy disagrees
#   - Treat opposing strategy signals as a Conflict.
#     This is Portfolio Diversification, not Conflict.
#
# This module is the SOLE gate for risk. Strategy + Unified Decision remain
# the source of trade direction. The architecture is:
#
#     Strategies
#        ↓
#     Independent Evaluation
#        ↓
#     Unified Decision
#        ↓
#     Portfolio Risk Authority  ← (this file)
#        ↓
#     Execution
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import threading

from core.settings import (
    MAX_RISK_TOTAL,
    MAX_LOT,
    BASE_RISK_DAILY,
    BASE_RISK_SMC,
    HARD_RISK_MAX_PER_TRADE,
    HARD_RISK_MAX_PER_TRADE_CEILING,
    MAX_DAILY_LOSS_USD,
    RISK_PER_TRADE_PERCENT,
    BASE_ACCOUNT_BALANCE,
    PORTFOLIO_RISK_AUTHORITY_ACTIVE,
    PORTFOLIO_RISK_AUTHORITY_CAN_REJECT,
    PORTFOLIO_RISK_AUTHORITY_CANNOT_REJECT_FOR,
    MAX_OPEN_TRADES,
    MAX_OPEN_PER_STRATEGY,
    PER_STRATEGY_MAX_OPEN_LIMITS,
    MAX_OPEN_PER_SYMBOL_DIRECTION,
    # === V3.5 Fairness: read UNIFIED_DEFAULTS from settings only ===
    ML_AUTHORITY_WEIGHT,
    ML_ADVISOR_WEIGHT,
    ML_BOOST_MAX_POINTS,
    ML_PENALTY_MAX_PTS,
)
from core.daily_loss_guard import get_daily_loss_status


# =============================================================================
# STATE — in-memory only; reset daily by the runtime layer if needed.
# =============================================================================

@dataclass
class PortfolioState:
    daily_loss_amount: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    day_start_balance: float = float(BASE_ACCOUNT_BALANCE)
    last_reset_day: Optional[str] = None
    emergency_stop: bool = False
    emergency_reason: str = ""
    open_trades: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    drawdown_peak_pnl: float = 0.0
    current_equity: float = float(BASE_ACCOUNT_BALANCE)


_STATE = PortfolioState()
_STATE_LOCK = threading.RLock()  # Reentrant lock for thread-safe access


def _with_state_lock(fn):
    """Decorator to ensure thread-safe access to _STATE.
    
    FER3ON ARCHITECTURE FIX #4: Race Condition Prevention
    Concurrent risk checks and trade updates could otherwise leave
    _STATE.open_trades inconsistent. This lock serializes state modifications.
    """
    def wrapper(*args, **kwargs):
        with _STATE_LOCK:
            return fn(*args, **kwargs)
    return wrapper


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x or default)
    except (TypeError, ValueError):
        return default


def get_portfolio_state() -> PortfolioState:
    return _STATE


def reset_portfolio_state(balance: Optional[float] = None) -> None:
    """Daily reset endpoint. Called by main.py at day-rollover."""
    if balance is not None:
        _STATE.day_start_balance = _safe_float(balance)
        _STATE.current_equity = float(balance)
    _STATE.daily_loss_amount = 0.0
    _STATE.daily_pnl = 0.0
    _STATE.drawdown_peak_pnl = 0.0
    _STATE.last_reset_day = _now_utc_str()
    if _STATE.emergency_reason == "DAILY_LOSS_LIMIT":
        _STATE.emergency_stop = False
        _STATE.emergency_reason = ""


def sync_portfolio_equity(balance: float) -> None:
    """Synchronize current authority equity with the broker account."""
    with _STATE_LOCK:
        value = _safe_float(balance, 0.0)
        if value > 0:
            _STATE.current_equity = value
            if not _STATE.last_reset_day:
                _STATE.day_start_balance = value


# =============================================================================
# RISK-ONLY DECISION DATACLASS
# =============================================================================

@dataclass
class RiskDecision:
    approved: bool = False
    # تقديري لأغراض القياس فقط (تحليلات authority_impact.py) — بيتحسب من
    # _round_lot_for_balance() اللي معادلة تقريبية مبنية على الرصيد والنسبة
    # المئوية بس، من غير أي معرفة بمسافة الـ SL الحقيقية. مش اللوت اللي فعليًا
    # بيتداول بيه. اللوت الحقيقي بييجي حصريًا من core/risk_manager.py::
    # calculate_smart_lot() (اللي بياخد sl_dist وquality_score وexec_grade
    # وغيرهم) وده اللي بيتبعت فعليًا لأمر التداول في main.py.
    final_lot_estimate: float = 0.0
    final_risk_percent: float = 0.0
    rejection_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    portfolio_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "final_lot_estimate": round(self.final_lot_estimate, 4),
            "final_risk_percent": round(self.final_risk_percent, 4),
            "rejection_reason": self.rejection_reason,
            "notes": list(self.notes),
            "portfolio_snapshot": self.portfolio_snapshot,
        }


# =============================================================================
# CORE API
# =============================================================================

def determine_base_risk_percent(strategy: str) -> float:
    """Base risk percent for the currently supported entry strategies."""
    s = (strategy or "UNKNOWN").upper()
    return {
        "DAILY": BASE_RISK_DAILY,
        "SMC":   BASE_RISK_SMC,
    }.get(s, RISK_PER_TRADE_PERCENT)


def compute_current_exposure() -> float:
    """Sum of risk_percent of currently open trades."""
    return sum(_safe_float(t.get("risk_percent", 0)) for t in _STATE.open_trades)


def count_open_by_strategy() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in _STATE.open_trades:
        s = str(t.get("strategy", "UNKNOWN")).upper()
        counts[s] = counts.get(s, 0) + 1
    return counts


def count_open_by_symbol_direction(*, symbol: str, direction: str) -> int:
    target_symbol = str(symbol or '').upper()
    target_direction = str(direction or '').upper()
    return sum(
        1 for trade in _STATE.open_trades
        if str(trade.get('symbol', '')).upper() == target_symbol
        and str(trade.get('direction', '')).upper() == target_direction
    )


def _daily_reset_if_needed() -> None:
    if _STATE.last_reset_day != _now_utc_str():
        if _STATE.emergency_reason == "DAILY_LOSS_LIMIT":
            _STATE.emergency_stop = False
            _STATE.emergency_reason = ""
        _STATE.daily_loss_amount = 0.0
        _STATE.daily_pnl = 0.0
        _STATE.drawdown_peak_pnl = 0.0
        _STATE.last_reset_day = _now_utc_str()


def evaluate_risk(
    *,
    strategy: str,
    direction: str,                # already decided upstream — Authority does NOT decide
    requested_risk_percent: float, # what upstream asked for
    ml_advice_boost: float = 0.0,  # ML advisory score delta (already capped upstream)
    ml_advice_enabled: bool = True,
    candidate_meta: Optional[Dict[str, Any]] = None,
) -> RiskDecision:
    """
    Single entry point for Portfolio Risk Authority.
    THREAD-SAFE: Uses _STATE_LOCK to serialize access.

    Inputs:
      - strategy:        DAILY | SMC | UNKNOWN
      - direction:       BUY | SELL (decided by strategy + unified_decision, NOT Authority)
      - requested_risk_percent: requested per-trade risk %
      - ml_advice_boost:    ±points within ±ML_BOOST_MAX_POINTS already (caller enforces this)
      - ml_advice_enabled:  TRUE if ML is REAL, FALSE if PARTIAL/DISABLED
      - candidate_meta:     optional metadata (rr_ratio, score, confidence, etc.)

    Returns:
      RiskDecision.approved=True  → proceed to Execution.
      RiskDecision.approved=False → blocked, rejection_reason explains why.
    """
    with _STATE_LOCK:  # FIX #4: Thread-safe access
        return _evaluate_risk_impl(strategy, direction, requested_risk_percent, ml_advice_boost, ml_advice_enabled, candidate_meta)


def _evaluate_risk_impl(
    strategy: str,
    direction: str,
    requested_risk_percent: float,
    ml_advice_boost: float = 0.0,
    ml_advice_enabled: bool = True,
    candidate_meta: Optional[Dict[str, Any]] = None,
) -> RiskDecision:
    """Internal implementation (called under _STATE_LOCK)."""
    decision = RiskDecision()
    decision.notes.append("PortfolioRiskAuthority:v3.5")

    if not PORTFOLIO_RISK_AUTHORITY_ACTIVE:
        decision.approved = True
        decision.final_risk_percent = _safe_float(requested_risk_percent)
        decision.final_lot_estimate = _round_lot_for_balance(decision.final_risk_percent)
        decision.notes.append("PORTFOLIO_RISK_AUTHORITY_DISABLED")
        return decision

    _daily_reset_if_needed()

    strat = (strategy or "UNKNOWN").upper()
    direction = (direction or "NONE").upper()
    meta = dict(candidate_meta or {})

    try:
        daily_status = get_daily_loss_status(
            symbol=str(meta.get("symbol") or "XAUUSD")
        )
    except Exception as exc:
        decision.rejection_reason = "DAILY_PNL_UNAVAILABLE"
        decision.notes.append(f"daily_pnl_source={exc}")
        decision.portfolio_snapshot = _snapshot()
        print(f"🛑 DAILY_LOSS_GUARD_BLOCK | MT5 daily PnL unavailable: {exc}")
        return decision

    _STATE.daily_pnl = float(daily_status["daily_pnl"])
    _STATE.daily_loss_amount = float(daily_status["daily_loss"])
    if _STATE.daily_loss_amount >= MAX_DAILY_LOSS_USD:
        _STATE.emergency_stop = True
        _STATE.emergency_reason = "DAILY_LOSS_LIMIT"

    # -------- Hard-stop / emergency -----------------------------------------
    if _STATE.emergency_stop:
        decision.notes.append(f"EMERGENCY_STOP_ACTIVE:{_STATE.emergency_reason}")
        decision.rejection_reason = (
            "DAILY_LOSS_LIMIT_HIT"
            if _STATE.emergency_reason == "DAILY_LOSS_LIMIT"
            else f"EMERGENCY_STOP:{_STATE.emergency_reason or 'UNKNOWN'}"
        )
        decision.portfolio_snapshot = _snapshot()
        return decision

    # -------- Daily loss limit -----------------------------------------------
    daily_loss_limit_amount = MAX_DAILY_LOSS_USD
    if _STATE.daily_loss_amount >= daily_loss_limit_amount:
        decision.rejection_reason = "DAILY_LOSS_LIMIT_HIT"
        decision.notes.append(
            f"daily_loss={_STATE.daily_loss_amount:.2f}>=limit={daily_loss_limit_amount:.2f}"
        )
        decision.portfolio_snapshot = _snapshot()
        return decision

    # -------- Open-position caps --------------------------------------------
    if len(_STATE.open_trades) >= MAX_OPEN_TRADES:
        decision.rejection_reason = "PORTFOLIO_MAX_OPEN_HIT"
        decision.notes.append(f"open={len(_STATE.open_trades)}>=max={MAX_OPEN_TRADES}")
        decision.portfolio_snapshot = _snapshot()
        return decision

    # This is the real per-strategy cap (see CERT-6 in
    # docs/history/FER3ON_FINAL_CHANGELOG.md) -- core.trade_executor's STEP 3
    # duplicates it as a defense-in-depth check at order-send time, and
    # core.risk_manager.evaluate_position_limits()'s per-strategy numbers are
    # NOT this cap and can't currently bind.
    per_strat = count_open_by_strategy()
    strategy_limit = int(PER_STRATEGY_MAX_OPEN_LIMITS.get(strat, MAX_OPEN_PER_STRATEGY))
    if per_strat.get(strat, 0) >= strategy_limit:
        decision.rejection_reason = "PER_STRATEGY_MAX_OPEN_HIT"
        decision.notes.append(
            f"{strat}_open={per_strat.get(strat,0)}>=max={strategy_limit}"
        )
        decision.portfolio_snapshot = _snapshot()
        return decision

    candidate_symbol = str(meta.get('symbol', '') or '').upper()
    if candidate_symbol:
        same_direction_open = count_open_by_symbol_direction(
            symbol=candidate_symbol,
            direction=direction,
        )
        if same_direction_open >= MAX_OPEN_PER_SYMBOL_DIRECTION:
            decision.rejection_reason = "SYMBOL_DIRECTION_MAX_OPEN_HIT"
            decision.notes.append(
                f"{candidate_symbol}_{direction}_open={same_direction_open}"
                f">=max={MAX_OPEN_PER_SYMBOL_DIRECTION}"
            )
            decision.portfolio_snapshot = _snapshot()
            return decision

    # -------- drawdown protection -------------------------------------------
    if _STATE.drawdown_peak_pnl > 0 and _STATE.daily_pnl < -_STATE.drawdown_peak_pnl * 0.5:
        # drawdown from peak > 50% — block only when peak is non-trivial
        decision.rejection_reason = "MAX_DRAWDOWN_HIT"
        decision.notes.append(
            f"peak_pnl={_STATE.drawdown_peak_pnl:.2f} "
            f"daily_pnl={_STATE.daily_pnl:.2f}"
        )
        decision.portfolio_snapshot = _snapshot()
        return decision

    # -------- Compute final risk --------------------------------------------
    base_risk = _safe_float(requested_risk_percent)
    base_risk = min(base_risk, HARD_RISK_MAX_PER_TRADE)
    base_risk = min(base_risk, HARD_RISK_MAX_PER_TRADE_CEILING)
    base_risk = min(base_risk, RISK_PER_TRADE_PERCENT)

    # -------- ML advisory delta ---------------------------------------------
    if ml_advice_enabled:
        # ensure caller already capped delta; cap again as safety net.
        boost = max(_safe_float(ml_advice_boost), ML_PENALTY_MAX_PTS)
        boost = min(boost, ML_BOOST_MAX_POINTS)
        # Advisory point delta translated into risk-percent delta
        # ±5 points ≈ ±0.05% risk (cap for safety).
        risk_delta = boost / 100.0
        base_risk = max(0.0, min(base_risk + risk_delta, HARD_RISK_MAX_PER_TRADE))
        decision.notes.append(
            f"ML_ADVISOR_BOOST={boost:+.1f}(weight={ML_ADVISOR_WEIGHT})"
        )
    else:
        decision.notes.append(f"ML_DISABLED(authority_weight={ML_AUTHORITY_WEIGHT})")

    # -------- Total exposure cap --------------------------------------------
    current_exp = compute_current_exposure()
    if current_exp + base_risk > MAX_RISK_TOTAL:
        headroom = max(0.0, MAX_RISK_TOTAL - current_exp)
        if headroom <= 0:
            decision.rejection_reason = "EXPOSURE_LIMIT_HIT"
            decision.notes.append(
                f"exp_used={current_exp:.3f}+req={base_risk:.3f}>max={MAX_RISK_TOTAL:.3f}"
            )
            decision.portfolio_snapshot = _snapshot()
            return decision
        base_risk = headroom
        decision.notes.append(f"EXPOSURE_TRIMMED_TO={base_risk:.3f}")

    # -------- Final lot (estimate only, see RiskDecision.final_lot_estimate) --
    final_lot_estimate = _round_lot_for_balance(base_risk)
    if final_lot_estimate <= 0:
        decision.rejection_reason = "LOT_CAP_HIT"
        # ملحوظة: هذا الفحص لا يعرف مسافة الـ SL الفعلية إطلاقًا (راجع
        # _round_lot_for_balance) — "risk_percent_rounds_to_zero_lot" أدق من
        # النص القديم "lot_too_small_for_sl_distance" الذي كان يوحي خطأً بأن
        # SL جزء من الحساب.
        decision.notes.append("risk_percent_rounds_to_zero_lot")
        decision.portfolio_snapshot = _snapshot()
        return decision

    decision.approved = True
    decision.final_risk_percent = base_risk
    decision.final_lot_estimate = final_lot_estimate
    decision.notes.append(f"strat={strat} dir={direction}")  # direction is for logging only
    decision.portfolio_snapshot = _snapshot()
    return decision


# =============================================================================
# LOT / ACCOUNT HELPERS
# =============================================================================

def _round_lot_for_balance(risk_percent: float) -> float:
    """Convert risk % → APPROXIMATE lot, for relative impact-measurement only.

    تحذير: هذه معادلة تقريبية (رصيد × نسبة مخاطرة) ولا تعرف شيئًا عن مسافة
    الـ SL الفعلية أو tick_value الرمز أو الجودة/الجلسة/exec_grade — عكس
    core/risk_manager.py::calculate_smart_lot() وهي المصدر الوحيد الموثوق
    لحجم اللوت الذي يُرسَل فعليًا لأمر التداول. لا تستخدم ناتج هذه الدالة
    (RiskDecision.final_lot_estimate) كأنه اللوت الحقيقي المُنفَّذ — استخدمه
    فقط في سياق قياس أثر Authority النسبي (analytics/authority_impact.py).
    """
    risk = _safe_float(risk_percent)
    if risk <= 0:
        return 0.0
    # Use a conservative proxy tuned for small capital and cent-style sizing.
    balance = max(float(_STATE.current_equity or 0.0), 1.0)
    if balance <= 100.0:
        approx = risk * balance / 100.0 / 100.0
    else:
        approx = risk * balance / 1000.0 / 10.0
    approx = max(0.01, approx)
    approx = min(approx, MAX_LOT)
    return round(approx, 2)


def record_trade_open(
    *,
    ticket: int,
    strategy: str,
    direction: str,
    lot: float,
    risk_percent: float,
    entry_price: float,
    sl: float,
    tp: float,
    symbol: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """THREAD-SAFE: Record a newly opened trade."""
    with _STATE_LOCK:  # FIX #4: Thread-safe access
        _record_trade_open_impl(ticket, strategy, direction, lot, risk_percent, entry_price, sl, tp, symbol, meta)


def _record_trade_open_impl(
    ticket: int,
    strategy: str,
    direction: str,
    lot: float,
    risk_percent: float,
    entry_price: float,
    sl: float,
    tp: float,
    symbol: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Internal implementation (called under _STATE_LOCK)."""
    _STATE.open_trades.append({
        "ticket": int(ticket),
        "strategy": strategy.upper(),
        "direction": direction.upper(),
        "symbol": str(symbol or "").upper(),
        "lot": float(lot),
        "risk_percent": float(risk_percent),
        "entry_price": float(entry_price),
        "sl": float(sl),
        "tp": float(tp),
        "open_time": datetime.now(timezone.utc).isoformat(),
        "meta": dict(meta or {}),
    })


def record_trade_close(*, ticket: int, profit: float) -> None:
    """THREAD-SAFE: Record trade closure and update daily PnL."""
    with _STATE_LOCK:  # FIX #4: Thread-safe access
        _record_trade_close_impl(ticket, profit)


def _record_trade_close_impl(ticket: int, profit: float) -> None:
    """Internal implementation (called under _STATE_LOCK)."""
    """Update daily loss + drawdown metrics from a closed trade."""
    open_trades = [t for t in _STATE.open_trades if t.get("ticket") != ticket]
    closed = next((t for t in _STATE.open_trades if t.get("ticket") == ticket), None)
    _STATE.open_trades = open_trades

    if not closed:
        return

    p = _safe_float(profit)
    _STATE.daily_pnl += p
    _STATE.weekly_pnl += p  # simple continual weekly tracking
    _STATE.daily_loss_amount = max(0.0, -_STATE.daily_pnl)
    if _STATE.daily_pnl > _STATE.drawdown_peak_pnl:
        _STATE.drawdown_peak_pnl = _STATE.daily_pnl

    closed_payload = dict(closed)
    closed_payload["profit"] = p
    closed_payload["close_time"] = datetime.now(timezone.utc).isoformat()
    _STATE.history.append(closed_payload)

    # Trigger daily emergency if limit reached
    daily_loss_limit_amount = MAX_DAILY_LOSS_USD
    if _STATE.daily_loss_amount >= daily_loss_limit_amount and not _STATE.emergency_stop:
        _STATE.emergency_stop = True
        _STATE.emergency_reason = "DAILY_LOSS_LIMIT"


def record_trade_partial_close(*, ticket: int, volume_closed: float, profit: float) -> None:
    """THREAD-SAFE: Record partial close with remaining exposure."""
    with _STATE_LOCK:  # FIX #4: Thread-safe access
        _record_trade_partial_close_impl(ticket, volume_closed, profit)


def _record_trade_partial_close_impl(ticket: int, volume_closed: float, profit: float) -> None:
    """Internal implementation (called under _STATE_LOCK)."""
    """Account for a partial close while retaining the remaining exposure."""
    closed = next((t for t in _STATE.open_trades
                   if int(t.get("ticket", -1)) == int(ticket)), None)
    if not closed:
        return
    original_lot = max(_safe_float(closed.get("lot")), 0.0)
    volume = min(max(_safe_float(volume_closed), 0.0), original_lot)
    if original_lot <= 0.0 or volume <= 0.0:
        return
    remaining_ratio = max(0.0, 1.0 - (volume / original_lot))
    closed["lot"] = round(original_lot * remaining_ratio, 8)
    closed["risk_percent"] = round(
        _safe_float(closed.get("risk_percent")) * remaining_ratio, 8
    )
    p = _safe_float(profit)
    _STATE.daily_pnl += p
    _STATE.weekly_pnl += p
    _STATE.daily_loss_amount = max(0.0, -_STATE.daily_pnl)
    if _STATE.daily_pnl > _STATE.drawdown_peak_pnl:
        _STATE.drawdown_peak_pnl = _STATE.daily_pnl


# =============================================================================
# DEFENSIVE RECONCILIATION (post-incident addition)
# =============================================================================
# record_trade_close() relies on the caller passing back the SAME ticket
# that was given to record_trade_open(). If that ever drifts out of sync —
# whatever the cause — open_trades grows unbounded and falsely blocks every
# future trade with PER_STRATEGY_MAX_OPEN_HIT / PORTFOLIO_MAX_OPEN_HIT, even
# with zero real positions on the account. This function is independent of
# any single bug: it trusts MT5's live position list as ground truth and
# drops anything in open_trades that MT5 no longer has open, regardless of
# why the mismatch happened.
#
# DATA-INTEGRITY FIX: this used to be prune-only -- it removed stale
# entries but never added a live position missing from open_trades. Since
# _STATE.open_trades is in-memory only, every process restart reset it to
# empty. Live positions had accumulated over multiple bot restarts, even though
# PER_STRATEGY_MAX_OPEN_HIT is supposed to cap each strategy at 1 concurrent
# position -- because each restart's cap check started counting from 0
# regardless of what was actually still open on the broker. Now also
# imports any live position not yet tracked, inferring strategy from its
# magic number, so the cap is correct immediately after a restart, not just
# within a single continuous run.
@_with_state_lock
def reconcile_with_live_positions(live_positions) -> Dict[str, int]:
    """
    `live_positions` must be an iterable of MT5 position objects/namedtuples
    (e.g. from mt5.positions_get()), each exposing .ticket, .magic, .volume,
    .price_open, .sl, .tp, .type (0=BUY, 1=SELL).

    Returns {"removed": n, "imported": m}.
    
    HIGH FIX #9: Robust error handling for import module failures.
    """
    try:
        from core.trade_identity import strategy_from_magic
    except ImportError as import_err:
        print(f'🛑 RECONCILE_CRITICAL: trade_identity module unavailable - {import_err}')
        print('⚠️ Reconciliation blocked to prevent position state divergence')
        raise RuntimeError(f'RECONCILE_IMPORT_FAILED: {import_err}')

    if live_positions is None:
        raise RuntimeError('POSITION_STATE_UNAVAILABLE')
    live_positions = list(live_positions)
    live_by_ticket = {int(getattr(p, "ticket", -1)): p for p in live_positions}

    before = len(_STATE.open_trades)
    _STATE.open_trades = [
        t for t in _STATE.open_trades if int(t.get("ticket", -1)) in live_by_ticket
    ]
    removed = before - len(_STATE.open_trades)

    tracked_tickets = {int(t.get("ticket", -1)) for t in _STATE.open_trades}
    imported = 0
    for ticket, pos in live_by_ticket.items():
        if ticket in tracked_tickets:
            continue
        strategy = strategy_from_magic(getattr(pos, "magic", None), default="UNKNOWN")
        direction = "SELL" if int(getattr(pos, "type", 0) or 0) == 1 else "BUY"
        _STATE.open_trades.append({
            "ticket": ticket,
            "strategy": strategy,
            "direction": direction,
            "symbol": str(getattr(pos, "symbol", "") or "").upper(),
            "lot": float(getattr(pos, "volume", 0) or 0),
            "risk_percent": 0.0,
            "entry_price": float(getattr(pos, "price_open", 0) or 0),
            "sl": float(getattr(pos, "sl", 0) or 0),
            "tp": float(getattr(pos, "tp", 0) or 0),
            "open_time": datetime.now(timezone.utc).isoformat(),
            "meta": {"source": "reconcile_import"},
        })
        imported += 1

    return {"removed": removed, "imported": imported}


# =============================================================================
# CONVENIENCE WRAPPERS (backward compatible with old fer3on_decision_authority)
# =============================================================================

def is_acceptable_rejection_reason(reason: Optional[str]) -> bool:
    """Used by callers that want to validate which reasons Authority is allowed to use."""
    if not reason:
        return True
    r = str(reason).upper()
    if r in (x.upper() for x in PORTFOLIO_RISK_AUTHORITY_CAN_REJECT):
        return True
    if r in (x.upper() for x in PORTFOLIO_RISK_AUTHORITY_CANNOT_REJECT_FOR):
        return False
    # Unknown reasons: permissive
    return True


def _snapshot() -> Dict[str, Any]:
    return {
        "daily_loss": round(_STATE.daily_loss_amount, 2),
        "daily_pnl": round(_STATE.daily_pnl, 2),
        "weekly_pnl": round(_STATE.weekly_pnl, 2),
        "open_count": len(_STATE.open_trades),
        "open_per_strat": count_open_by_strategy(),
        "exposure_pct": round(compute_current_exposure(), 4),
        "emergency": _STATE.emergency_stop,
        "emergency_reason": _STATE.emergency_reason,
        "max_open": MAX_OPEN_TRADES,
        "max_open_per_strategy": dict(PER_STRATEGY_MAX_OPEN_LIMITS),
        "max_open_per_symbol_direction": MAX_OPEN_PER_SYMBOL_DIRECTION,
        "max_daily_loss_amount": MAX_DAILY_LOSS_USD,
        "v3_5_phase": "phase_1_stabilization",
    }


# =============================================================================
# TEST HELPERS
# =============================================================================

def __test_reset__() -> None:
    _STATE.open_trades = []
    _STATE.history = []
    _STATE.daily_loss_amount = 0.0
    _STATE.daily_pnl = 0.0
    _STATE.weekly_pnl = 0.0
    _STATE.drawdown_peak_pnl = 0.0
    _STATE.emergency_stop = False
    _STATE.emergency_reason = ""
    _STATE.last_reset_day = _now_utc_str()
