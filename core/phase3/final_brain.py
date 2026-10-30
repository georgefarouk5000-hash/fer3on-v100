# =============================================================================
# FER3ON — PHASE 3 | FINAL_BRAIN (Shadow Mode)
# =============================================================================
# الدور: طبقة الموافقة النهائية المؤسسية.
# الوضع الحالي: SHADOW ONLY — لا سلطة تنفيذية حتى اكتمال شروط التفعيل.
#
# ما يفعله FINAL_BRAIN:
#   - يستقبل قرار المنظومة الحالية (كما هو، بدون تغيير)
#   - يحسب approval_score مؤسسي بناءً على مدخلات متعددة
#   - يسجّل قراره shadow (موافقة / رفض / ترتيب)
#   - يقارن قراره بالقرار الفعلي لقياس الدقة
#   - يبني قاعدة بيانات لتقييم جاهزية التفعيل
#
# ما لا يفعله الآن:
#   - لا يحجب أي صفقة
#   - لا يعدّل direction logic
#   - لا يغيّر entry conditions
#   - لا يُفعَّل live قبل اكتمال PHASE3_REQUIRED_CLOSED_TRADES
# =============================================================================

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    FINAL_BRAIN_ENABLED,
    FINAL_BRAIN_LIVE_AUTHORITY,
    FINAL_BRAIN_MAX_SETUPS_PER_CYCLE,
    FINAL_BRAIN_MIN_APPROVAL_SCORE,
    FINAL_BRAIN_MIN_REJECT_SCORE,
    FINAL_BRAIN_RANKING_ENABLED,
    FINAL_BRAIN_SHADOW_LOG,
    PHASE3_FINAL_BRAIN_DIR,
    PHASE3_LIVE_AUTHORITY,
    PHASE3_REQUIRED_CLOSED_TRADES,
    PHASE3_REQUIRED_FALSE_REJECT_MAX,
    PHASE3_REQUIRED_SHADOW_CYCLES,
    PHASE3_REQUIRED_WIN_RATE_MIN,
)

_SHADOW_LOG_FILE = os.path.join(PHASE3_FINAL_BRAIN_DIR, "shadow_decisions.jsonl")
_STATE_FILE = os.path.join(PHASE3_FINAL_BRAIN_DIR, "final_brain_state.json")

# Guard: هذا المكوّن لا يُفعَّل live أبداً في Phase 3 الأولى
assert not FINAL_BRAIN_LIVE_AUTHORITY, (
    "FINAL_BRAIN: Live authority is disabled in Phase 3. "
    "Set FINAL_BRAIN_LIVE_AUTHORITY=True only after completing all activation requirements."
)
assert not PHASE3_LIVE_AUTHORITY, (
    "PHASE3: Live authority is globally disabled. "
    "Validate all shadow performance metrics before enabling."
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class FinalBrainInput:
    """مدخلات FINAL_BRAIN من المنظومة الحالية."""
    strategy: str = "UNKNOWN"
    signal: str = "NONE"
    symbol: str = "XAUUSD"
    quality_score: float = 0.0
    confidence_pct: float = 0.0
    composite_score: float = 0.0
    actual_decision: str = "UNKNOWN"   # القرار الفعلي من المنظومة
    portfolio_brain_score: float = 50.0
    gold_context_score: float = 50.0
    ml_health_score: float = 50.0
    strategy_dna_rank: float = 50.0
    session: str = "UNKNOWN"
    market_regime: str = "UNKNOWN"
    timestamp: float = field(default_factory=time.time)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FinalBrainDecision:
    """قرار FINAL_BRAIN (shadow)."""
    shadow_decision: str = "SHADOW_APPROVE"   # SHADOW_APPROVE / SHADOW_REJECT / SHADOW_WAIT
    approval_score: float = 0.0
    confidence: float = 0.0
    ranking_position: int = 1
    reasoning: List[str] = field(default_factory=list)
    matched_actual: bool = False          # هل القرار الـ shadow يتطابق مع الفعلي؟
    false_rejection: bool = False         # هل رفضنا صفقة كانت ناجحة؟
    missed_winner: bool = False           # هل ضيّعنا فرصة رابحة؟
    avoided_loser: bool = False           # هل تجنّبنا صفقة خاسرة؟
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

_DEFAULT_STATE = {
    "version": "phase3.0",
    "total_shadow_cycles": 0,
    "total_approvals": 0,
    "total_rejections": 0,
    "total_waits": 0,
    "matched_actual_count": 0,
    "false_rejections": 0,
    "missed_winners": 0,
    "avoided_losers": 0,
    "approval_accuracy": 0.0,
    "false_rejection_rate": 0.0,
    "readiness_score": 0.0,
    "live_ready": False,
    "last_updated": 0,
}


def _ensure_dirs() -> None:
    os.makedirs(PHASE3_FINAL_BRAIN_DIR, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(_STATE_FILE):
        return dict(_DEFAULT_STATE)
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULT_STATE, **data}
    except Exception:
        return dict(_DEFAULT_STATE)


def _save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    state["last_updated"] = time.time()
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[FINAL_BRAIN] State save error: {e}")


def _log_shadow_decision(inp: FinalBrainInput, decision: FinalBrainDecision) -> None:
    if not FINAL_BRAIN_SHADOW_LOG:
        return
    _ensure_dirs()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "candidate_id": (inp.extra or {}).get("candidate_id"),
        "input": asdict(inp),
        "decision": asdict(decision),
    }
    try:
        from core.trade_event_ledger import append_candidate_record
        append_candidate_record(_SHADOW_LOG_FILE, record)
    except Exception as e:
        print(f"[FINAL_BRAIN] Log error: {e}")


# =============================================================================
# CORE SCORING
# =============================================================================

def _compute_approval_score(inp: FinalBrainInput) -> float:
    """
    يحسب approval_score مؤسسي مركّب.
    لا يخترع اتجاهاً جديداً — يصادق أو يرفض الاتجاه القادم من المنظومة.
    """
    score = 0.0
    reasons = []

    # 1) جودة الإعداد الأساسية (40% من الوزن)
    quality_contribution = float(inp.quality_score or 0) * 0.40
    score += quality_contribution
    reasons.append(f"Quality={float(inp.quality_score or 0):.1f} → +{quality_contribution:.1f}")

    # 2) الثقة (25% من الوزن)
    confidence_contribution = float(inp.confidence_pct or 0) * 0.25
    score += confidence_contribution
    reasons.append(f"Confidence={float(inp.confidence_pct or 0):.1f} → +{confidence_contribution:.1f}")

    # 3) Portfolio Brain (15% من الوزن)
    portfolio_contribution = float(inp.portfolio_brain_score or 50) * 0.15
    score += portfolio_contribution
    reasons.append(f"PortfolioBrain={float(inp.portfolio_brain_score or 50):.1f} → +{portfolio_contribution:.1f}")

    # 4) Gold Context (10% من الوزن)
    gold_contribution = float(inp.gold_context_score or 50) * 0.10
    score += gold_contribution
    reasons.append(f"GoldContext={float(inp.gold_context_score or 50):.1f} → +{gold_contribution:.1f}")

    # 5) ML Health (5% من الوزن)
    ml_contribution = float(inp.ml_health_score or 50) * 0.05
    score += ml_contribution
    reasons.append(f"MLHealth={float(inp.ml_health_score or 50):.1f} → +{ml_contribution:.1f}")

    # 6) Strategy DNA Rank (5% من الوزن)
    dna_contribution = float(inp.strategy_dna_rank or 50) * 0.05
    score += dna_contribution
    reasons.append(f"StrategyDNA={float(inp.strategy_dna_rank or 50):.1f} → +{dna_contribution:.1f}")

    return min(100.0, max(0.0, score))


def _determine_shadow_decision(approval_score: float) -> str:
    if approval_score >= FINAL_BRAIN_MIN_APPROVAL_SCORE:
        return "SHADOW_APPROVE"
    elif approval_score < FINAL_BRAIN_MIN_REJECT_SCORE:
        return "SHADOW_REJECT"
    else:
        return "SHADOW_WAIT"


# =============================================================================
# PUBLIC API
# =============================================================================

def evaluate_shadow(inp: FinalBrainInput) -> FinalBrainDecision:
    """
    التقييم الرئيسي لـ FINAL_BRAIN في وضع Shadow.
    يُستدعى بعد قرار المنظومة — لا يُغيّر القرار الفعلي.
    """
    if not FINAL_BRAIN_ENABLED:
        return FinalBrainDecision(
            shadow_decision="SHADOW_DISABLED",
            approval_score=50.0,
            reasoning=["FINAL_BRAIN is disabled in settings"],
        )

    approval_score = _compute_approval_score(inp)
    shadow_decision = _determine_shadow_decision(approval_score)

    # مقارنة مع القرار الفعلي
    actual_is_trade = inp.actual_decision in ("FULL", "REDUCED", "MICRO")
    shadow_is_approve = shadow_decision == "SHADOW_APPROVE"
    matched_actual = actual_is_trade == shadow_is_approve

    decision = FinalBrainDecision(
        shadow_decision=shadow_decision,
        approval_score=approval_score,
        confidence=min(100.0, approval_score * 1.1),
        ranking_position=1 if FINAL_BRAIN_RANKING_ENABLED else 0,
        reasoning=[
            f"ApprovalScore={approval_score:.2f}",
            f"Threshold: approve>={FINAL_BRAIN_MIN_APPROVAL_SCORE}, reject<{FINAL_BRAIN_MIN_REJECT_SCORE}",
            f"ActualDecision={inp.actual_decision}",
            f"Matched={matched_actual}",
        ],
        matched_actual=matched_actual,
    )

    # تحديث الحالة
    state = _load_state()
    state["total_shadow_cycles"] += 1
    if shadow_decision == "SHADOW_APPROVE":
        state["total_approvals"] += 1
    elif shadow_decision == "SHADOW_REJECT":
        state["total_rejections"] += 1
    else:
        state["total_waits"] += 1
    if matched_actual:
        state["matched_actual_count"] += 1

    total = state["total_shadow_cycles"]
    state["approval_accuracy"] = (
        round(state["matched_actual_count"] / total, 4) if total > 0 else 0.0
    )
    state["readiness_score"] = _compute_readiness_score(state)
    _save_state(state)

    # تسجيل shadow
    _log_shadow_decision(inp, decision)

    print(
        f"[FINAL_BRAIN SHADOW] {shadow_decision} | Score={approval_score:.1f} | "
        f"Actual={inp.actual_decision} | Matched={matched_actual} | "
        f"Cycles={total}"
    )

    return decision


def record_trade_outcome(ticket: int, was_winner: bool, shadow_decision: str) -> None:
    """
    يُسجّل نتيجة الصفقة الفعلية لقياس:
    - false_rejection: رفضنا shadow صفقة رابحة
    - missed_winner: ضيّعنا فرصة رابحة
    - avoided_loser: رفضنا shadow صفقة خاسرة
    """
    state = _load_state()
    shadow_rejected = shadow_decision == "SHADOW_REJECT"

    if shadow_rejected and was_winner:
        state["false_rejections"] += 1
        state["false_rejection_rate"] = (
            state["false_rejections"] / max(1, state["total_rejections"])
        )
        print(f"[FINAL_BRAIN] False rejection detected | ticket={ticket}")
    elif shadow_rejected and not was_winner:
        state["avoided_losers"] += 1
        print(f"[FINAL_BRAIN] Avoided loser | ticket={ticket}")

    _save_state(state)


def _compute_readiness_score(state: Dict[str, Any]) -> float:
    """يحسب درجة الجاهزية للترقية من Shadow إلى Live."""
    score = 0.0
    total_cycles = state.get("total_shadow_cycles", 0)

    # 1) عدد دورات Shadow كافية (30%)
    shadow_progress = min(1.0, total_cycles / max(1, PHASE3_REQUIRED_SHADOW_CYCLES))
    score += shadow_progress * 30

    # 2) دقة الموافقة (40%)
    accuracy = state.get("approval_accuracy", 0.0)
    score += accuracy * 40

    # 3) معدل الرفض الخاطئ منخفض (30%)
    false_rejection_rate = state.get("false_rejection_rate", 1.0)
    if false_rejection_rate <= PHASE3_REQUIRED_FALSE_REJECT_MAX:
        score += 30
    else:
        score += max(0, 30 * (1 - false_rejection_rate))

    return round(score, 2)


def get_readiness_report() -> Dict[str, Any]:
    """تقرير جاهزية FINAL_BRAIN للترقية إلى Live."""
    state = _load_state()
    return {
        "component": "FINAL_BRAIN",
        "mode": "SHADOW",
        "live_authority": FINAL_BRAIN_LIVE_AUTHORITY,
        "total_shadow_cycles": state.get("total_shadow_cycles", 0),
        "approval_accuracy": state.get("approval_accuracy", 0.0),
        "false_rejection_rate": state.get("false_rejection_rate", 0.0),
        "false_rejections": state.get("false_rejections", 0),
        "avoided_losers": state.get("avoided_losers", 0),
        "readiness_score": state.get("readiness_score", 0.0),
        "live_ready": state.get("readiness_score", 0.0) >= 80.0,
        "requirements": {
            "shadow_cycles_required": PHASE3_REQUIRED_SHADOW_CYCLES,
            "shadow_cycles_done": state.get("total_shadow_cycles", 0),
            "false_reject_max": PHASE3_REQUIRED_FALSE_REJECT_MAX,
            "current_false_reject": state.get("false_rejection_rate", 0.0),
        },
    }
