# =============================================================================
# FER3ON — PHASE 5 | OPPORTUNITY ALLOCATOR (capital + opportunity engine)
# =============================================================================
# Ranks opportunities and allocates risk instead of "trade every signal":
#   Opportunity Score = Edge x Probability x Market Space x Execution Quality
#                       x Regime Fit        (all 0..1 -> score 0..1)
#   Daily states: SURVIVAL / NORMAL / OPPORTUNITY / PROTECTION (+Profit Lock)
#   Risk tiers:   0.25R normal / 0.50R good / 0.75R excellent — a tier above
#                 base is unlocked ONLY by sufficient REAL, attributed
#                 results (decision_ledger buckets), never by confidence.
#
# ADVISORY BY DEFAULT (PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED = False):
# evaluations are computed + logged, live decisions untouched.
#
# SAFETY CONTRACT: never raises; imports NO execution code (no MT5 /
# trade_executor); callers pass plain dicts, get plain dicts back.
#
# [FER3ON-2026-08-31] ENHANCED: Added rank_opportunity() for direct sizing,
# not just advisory scoring. Gradual rejection: EXCELLENT→GOOD→FAIR→WEAK.
# =============================================================================
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _cfg(name: str, default: Any) -> Any:
    try:
        import core.settings as _s
        return getattr(_s, name, default)
    except Exception:
        return default


def _enabled() -> bool:
    return bool(_cfg("PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED", True))


def _live() -> bool:
    return bool(_cfg("PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED", False))


def _log_path() -> str:
    return str(_cfg("PHASE5_ALLOCATOR_LOG_PATH",
                    "data/analytics/opportunity_allocator/evaluations.jsonl"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# [FER3ON-2026-08-31] SIMPLIFIED RANKING (for direct sizing)
# ---------------------------------------------------------------------------

@dataclass
@dataclass
class OpportunityRank:
    """Result of ranking a single opportunity for sizing.
    
    ARCHITECTURE NOTE: lot_multiplier and risk_adjustment are semantically identical
    and must always remain equal. They are kept as separate fields for API clarity:
    - lot_multiplier: used to scale trading volume
    - risk_adjustment: used to scale risk percentage
    Both receive the same value (1.0 → EXCELLENT, 0.7 → GOOD, 0.4 → FAIR, 0.0 → WEAK).
    If they ever diverge, it indicates a bug.
    """
    grade: str  # EXCELLENT | GOOD | FAIR | WEAK
    score: float  # 0-100
    lot_multiplier: float  # 1.0 | 0.70 | 0.40 | 0.0
    risk_adjustment: float  # 1.0 | 0.70 | 0.40 | 0.0 (must == lot_multiplier)
    reasoning: str
    should_reject: bool
    
    def __post_init__(self):
        """Validate that lot_multiplier == risk_adjustment (architectural invariant)."""
        if abs(self.lot_multiplier - self.risk_adjustment) > 1e-6:
            raise ValueError(
                f"OpportunityRank invariant violated: "
                f"lot_multiplier={self.lot_multiplier} != risk_adjustment={self.risk_adjustment}"
            )


def effective_risk_adjustment(
    rank: OpportunityRank,
    *,
    live_enabled: bool,
) -> float:
    """Return allocator sizing influence only after explicit live promotion."""
    return rank.risk_adjustment if live_enabled else 1.0


def rank_opportunity(
    quality_score: float = 0.0,
    confidence_pct: float = 0.0,
    market_regime: str = "UNKNOWN",
    session: str = "UNKNOWN",
    smc_strength: float = 0.0,
    mtf_strength: int = 0,
    execution_grade: str = "UNKNOWN",
    daily_bias_alignment: bool = False,
    candidate_id: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    direction: Optional[str] = None,
    decision_bar_time: Optional[Any] = None,
) -> OpportunityRank:
    """
    Rank opportunity for sizing: EXCELLENT(100%) → GOOD(70%) → FAIR(40%) → WEAK(reject).
    
    Gradual rejection, not binary: weak signals downsize but aren't rejected if
    context is good enough.
    """
    try:
        q = max(0, min(100, float(quality_score or 0)))
        c = max(0, min(100, float(confidence_pct or 0)))
        
        # Base score: quality dominates, confidence secondary
        base_score = q * 0.65 + c * 0.35
        
        # Context multipliers
        regime_mult = {
            'TRENDING': 1.10, 'RANGING': 0.85, 'VOLATILE': 0.70,
            'CRISIS': 0.50, 'UNKNOWN': 0.95,
        }.get(str(market_regime or 'UNKNOWN').upper(), 0.95)
        
        session_mult = {
            'LONDON': 1.15, 'NEWYORK': 1.10, 'OVERLAP': 1.20,
            'ASIA': 0.85, 'OFF_HOURS': 0.70, 'UNKNOWN': 1.00,
        }.get(str(session or 'UNKNOWN').upper(), 1.00)
        
        context_score = base_score * regime_mult * session_mult
        
        # Bonuses for confluence
        bonus = 0.0
        if float(smc_strength or 0) >= 7.0:
            bonus += 5.0
        if int(mtf_strength or 0) >= 8:
            bonus += 3.0
        if daily_bias_alignment:
            bonus += 4.0
        if str(execution_grade or '').upper() in ('ELITE', 'A+', 'A'):
            bonus += 2.0
        
        final_score = min(100, context_score + bonus)
        
        # Grade and sizing
        if final_score >= 85:
            grade, lot_m, risk_a = 'EXCELLENT', 1.0, 1.0
        elif final_score >= 70:
            grade, lot_m, risk_a = 'GOOD', 0.70, 0.70
        elif final_score >= 55:
            grade, lot_m, risk_a = 'FAIR', 0.40, 0.40
        else:
            grade, lot_m, risk_a = 'WEAK', 0.0, 0.0
        
        reason = (
            f"q={q:.0f} c={c:.0f} base={base_score:.0f} "
            f"regime×{regime_mult:.2f} session×{session_mult:.2f} "
            f"ctx={context_score:.0f} bonus={bonus:.0f} → {final_score:.0f}"
        )
        
        result = OpportunityRank(
            grade=grade,
            score=final_score,
            lot_multiplier=lot_m,
            risk_adjustment=risk_a,
            reasoning=reason,
            should_reject=(grade == 'WEAK'),
        )
        if candidate_id:
            _log_evaluation({
                "candidate_id": candidate_id,
                "signal_id": candidate_id,
                "symbol": symbol,
                "direction": str(direction or "").upper() or None,
                "strategy": str(strategy or "UNKNOWN").upper(),
                "decision_bar_time": decision_bar_time,
                "grade": result.grade,
                "score": result.score,
                "lot_multiplier": result.lot_multiplier,
                "risk_adjustment": result.risk_adjustment,
                "action": "SKIP" if result.should_reject else "RANKED",
                "reason": result.reasoning,
                "logged_at": _utc_now_iso(),
            })
        return result
    except Exception as e:
        # Fail-closed
        return OpportunityRank(
            grade='WEAK', score=0.0, lot_multiplier=0.0, risk_adjustment=0.0,
            reasoning=f'rank_error: {str(e)}', should_reject=True,
        )


def apply_sizing(
    rank: OpportunityRank,
    base_lot: float = 0.02,
    base_risk_percent: float = 0.75,
) -> Dict[str, Any]:
    """Apply rank's multipliers to base lot and risk."""
    try:
        final_lot = base_lot * rank.lot_multiplier
        final_risk = base_risk_percent * rank.risk_adjustment
        
        return {
            'final_lot': round(max(0.001, final_lot), 4),
            'final_risk_percent': round(max(0.01, final_risk), 3),
            'grade': rank.grade,
            'lot_multiplier': rank.lot_multiplier,
            'risk_adjustment': rank.risk_adjustment,
            'reasoning': rank.reasoning,
        }
    except Exception as e:
        return {
            'final_lot': 0.0,
            'final_risk_percent': 0.0,
            'grade': 'WEAK',
            'lot_multiplier': 0.0,
            'risk_adjustment': 0.0,
            'reasoning': f'sizing_error: {str(e)}',
        }




# ---------------------------------------------------------------------------
# Opportunity Score
# ---------------------------------------------------------------------------

def _clamp01(x: Any) -> float:
    try:
        v = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, v))


def compute_opportunity_score(edge: Any, probability: Any, market_space: Any,
                              execution_quality: Any, regime_fit: Any) -> float:
    """Multiplicative score in [0,1]. Any zero factor kills the opportunity —
    by design: a great setup with terrible execution is still a no-trade."""
    try:
        s = (_clamp01(edge) * _clamp01(probability) * _clamp01(market_space)
             * _clamp01(execution_quality) * _clamp01(regime_fit))
        return round(s, 6)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Daily state machine + Profit Lock
# ---------------------------------------------------------------------------

def classify_daily_state(daily_pnl: Any = 0.0,
                         consecutive_losses: Any = 0,
                         regime_clear: bool = True) -> str:
    """SURVIVAL / NORMAL / OPPORTUNITY / PROTECTION.
    PROTECTION has priority over OPPORTUNITY: once the day is won, the job
    is to KEEP it (Profit Lock), not to chase more."""
    try:
        pnl = float(daily_pnl or 0.0)
    except Exception:
        pnl = 0.0
    try:
        losses = int(consecutive_losses or 0)
    except Exception:
        losses = 0
    lock_at = float(_cfg("DAILY_PROFIT_LOCK_DOLLARS", 30.0))
    survival_after = int(_cfg("DAILY_SURVIVAL_AFTER_LOSSES", 2))
    if losses >= survival_after:
        return "SURVIVAL"
    if pnl >= lock_at:
        return "PROTECTION"          # Profit Lock engaged
    if pnl > 0 and regime_clear:
        return "OPPORTUNITY"
    return "NORMAL"


def profit_lock_active(daily_pnl: Any = 0.0) -> bool:
    return classify_daily_state(daily_pnl) == "PROTECTION"


# ---------------------------------------------------------------------------
# Risk allocation
# ---------------------------------------------------------------------------

def recommend_risk_r(score: Any,
                     bucket_stats: Optional[Dict[str, Any]] = None) -> float:
    """0.0 / 0.25 / 0.50 / 0.75 R.
    Above-base tiers require BOTH a high score AND sufficient attributed
    real results (ledger bucket with enough samples + positive expectancy).
    Confidence alone NEVER raises risk."""
    s = _clamp01(score)
    base = float(_cfg("ALLOCATOR_BASE_RISK_R", 0.25))
    good_at = float(_cfg("ALLOCATOR_GOOD_SCORE", 0.25))
    excellent_at = float(_cfg("ALLOCATOR_EXCELLENT_SCORE", 0.40))
    min_samples = int(_cfg("ALLOCATOR_MIN_SAMPLES", 30))
    if s <= 0.0:
        return 0.0
    proven = False
    try:
        b = bucket_stats or {}
        n = int(b.get("n", 0) or 0)
        wr = float(b.get("win_rate", 0) or 0)
        pnl = float(b.get("pnl", 0) or 0)
        proven = (n >= min_samples) and (wr > 0.5) and (pnl > 0)
    except Exception:
        proven = False
    if s >= excellent_at and proven:
        return round(base * 3, 4)   # 0.75R
    if s >= good_at and proven:
        return round(base * 2, 4)   # 0.50R
    return round(base, 4)           # 0.25R


# ---------------------------------------------------------------------------
# Full evaluation (advisory)
# ---------------------------------------------------------------------------

def evaluate_opportunity(snapshot: Optional[Dict[str, Any]] = None,
                         daily_pnl: Any = 0.0,
                         consecutive_losses: Any = 0,
                         regime_clear: bool = True,
                         bucket_stats: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
    """Advisory evaluation. Returns a plain dict; logs it; NEVER touches the
    live decision unless the LIVE flag is on AND the caller consumes it."""
    out: Dict[str, Any] = {
        "enabled": False, "live": False, "action": "SKIP",
        "score": 0.0, "daily_state": "NORMAL", "risk_r": 0.0,
        "reason": "ALLOCATOR_DISABLED",
    }
    try:
        if not _enabled():
            return out
        snap = snapshot or {}
        score = compute_opportunity_score(
            snap.get("edge", snap.get("confidence", 0)),
            snap.get("probability", snap.get("win_probability", 0)),
            snap.get("market_space", 0),
            snap.get("execution_quality", 0),
            snap.get("regime_fit", 0),
        )
        state = classify_daily_state(daily_pnl, consecutive_losses, regime_clear)
        risk_r = recommend_risk_r(score, bucket_stats)

        action, reason = "TAKE", "SCORE_OK"
        min_score = float(_cfg("ALLOCATOR_MIN_SCORE", 0.10))
        if state == "SURVIVAL":
            action, reason, risk_r = "SKIP", "DAILY_SURVIVAL", 0.0
        elif state == "PROTECTION":
            exceptional = float(_cfg("ALLOCATOR_EXCEPTIONAL_SCORE", 0.50))
            if score < exceptional:
                action, reason, risk_r = "SKIP", "PROFIT_LOCK_ACTIVE", 0.0
            else:
                risk_r = min(risk_r, float(_cfg("ALLOCATOR_BASE_RISK_R", 0.25)))
                reason = "PROTECTION_EXCEPTIONAL_ONLY"
        elif score < min_score:
            action, reason, risk_r = "SKIP", "SCORE_BELOW_MIN", 0.0

        out.update({
            "enabled": True, "live": _live(), "action": action,
            "score": score, "daily_state": state, "risk_r": risk_r,
            "reason": reason,
            "signal_id": snap.get("signal_id"),
            "strategy": snap.get("strategy"), "session": snap.get("session"),
            "regime": snap.get("regime"),
            "logged_at": _utc_now_iso(),
        })
        _log_evaluation(out)
        return out
    except Exception:
        return out


def _log_evaluation(rec: Dict[str, Any]) -> bool:
    try:
        p = _log_path()
        from core.trade_event_ledger import append_candidate_record
        return append_candidate_record(p, rec)
    except Exception:
        return False
