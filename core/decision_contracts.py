# =============================================================================
# FER3ON — DECISION CONTRACTS (Phase 0)
# =============================================================================
# الدور: تثبيت أشكال بيانات موحّدة (contracts) بدل تمرير قواميس غير منظمة
# بين main.py / trade_executor.py / sl_tp_finalizer.py.
#
# هذا الملف إضافي بالكامل: تعريفات بيانات (dataclasses) بس، صفر منطق تنفيذ،
# صفر لمس لأي مسار حي. مفيش أي كود موجود بيستورد منه لسه — الاستيراد
# والاستخدام الفعلي هي المرحلة اللي بعد كده، مش جزء من الملف ده.
#
# كل عقد يحمل build_id + decision_snapshot_id إلزاميًا (زي ما اتفقنا) عشان
# أي قرار يتربط بنسخة الكود اللي أنتجته من أول لحظة.
#
# التوافق مع الكود الحالي: كل عقد فيه .to_dict() عشان يتحول لقاموس عادي
# يتقبله أي دالة موجودة بتستنى dict — تبني تدريجي مش قطع مفاجئ.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from core.settings import BUILD_ID as _BUILD_ID
except Exception:  # pragma: no cover
    _BUILD_ID = None


def new_decision_snapshot_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_fields() -> Dict[str, Any]:
    return {
        "build_id": _BUILD_ID or "",
        "decision_snapshot_id": new_decision_snapshot_id(),
        "created_at": _now_iso(),
    }


class DecisionState(str, Enum):
    """
    [FER3ON-FIX-2026-08-29] يحل الخطر رقم 8 من "أخطر 10 مخاطر": حاليًا
    القرار بينتهي غالبًا لـAPPROVE أو HARD_BLOCK بس، فأي فرصة صحيحة
    الاتجاه لكن التنفيذ مش جاهز ليها (زي انتظار retest) بتظهر كأنها فشل
    كامل. التعريف هنا بس — مفيش أي كود لسه بيستخدم WAIT_RETEST/
    WAIT_CONFIRMATION فعليًا في مسار حي؛ ده الخطوة التالية (توحيد
    الاستراتيجيات) مش جزء من العقود.
    """
    REJECTED = "REJECTED"
    WAIT_RETEST = "WAIT_RETEST"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"


class ExitReason(str, Enum):
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    SL_HIT = "SL_HIT"
    BREAK_EVEN = "BREAK_EVEN"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_EXIT_NO_PROGRESS = "EXIT_TIME_NO_PROGRESS"
    EVIDENCE_INVALIDATED = "EXIT_EVIDENCE_INVALIDATED"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class SLSource(str, Enum):
    STRUCTURE_SWING = "SL_STRUCTURE_SWING"
    ORDER_BLOCK = "SL_STRUCTURE_OB"
    FVG_LIQUIDITY = "SL_STRUCTURE_FVG"
    ATR_FALLBACK = "SL_FALLBACK_ATR"
    REJECTED_TOO_WIDE = "SL_REJECTED_TOO_WIDE"
    STRUCTURE_INVALID = "SL_STRUCTURE_INVALID"
    CAPPED_BY_RISK = "SL_CAPPED_BY_RISK"


@dataclass
class SignalSnapshot:
    """أول عقد في السلسلة — لازم كل استراتيجية نشطة تنتج
    نفس الشكل ده (المرحلة الأولى في الترتيب المقترح، مش منفّذة هنا)."""
    signal_id: str
    symbol: str
    strategy: str
    direction: str  # BUY | SELL
    signal_time: str
    entry_reference: float = 0.0
    regime: str = ""
    session: str = ""
    structure: Dict[str, Any] = field(default_factory=dict)
    liquidity: Dict[str, Any] = field(default_factory=dict)
    atr: float = 0.0
    confidence: float = 0.0
    quality: float = 0.0
    execution_grade: str = ""
    mtf_alignment: str = ""
    raw_signal_reason: str = ""
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskDecision:
    """
    [يخص الخطر رقم 6]: الحقول دي لازم تتعرف *بعد* ما SL/lot النهائيين
    يتحسبوا، مش قبلهم — الترتيب الفعلي (استدعاء evaluate_risk قبل أو
    بعد calculate_smart_lot) خارج نطاق العقد ده، محتاج تتبع منفصل في
    main.py/portfolio_risk_authority.py.
    """
    signal_id: str
    approved: bool
    account_risk_budget: float = 0.0
    daily_remaining_risk: float = 0.0
    portfolio_remaining_risk: float = 0.0
    actual_dollar_risk: Optional[float] = None
    lot: Optional[float] = None
    rejection_reason: str = ""
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinalEntryPlan:
    """
    الشكل المطلوب حرفيًا في الوثيقة (قسم "إعادة حساب SL/TP في أكثر من
    طبقة"): بعد إنتاجه من sl_tp_finalizer، لا يُسمح لأي طبقة بإعادة حساب
    الأسعار أو المسافات — التنفيذ يرسل الخطة كما هي. الإنفاذ الفعلي لهذا
    القيد (منع طبقات تانية من التعديل) مش جزء من تعريف العقد نفسه.
    """
    signal_id: str
    entry_price: float
    sl_price: float
    tp_prices: List[float]
    sl_distance: float
    risk_amount: float
    rr: float
    source: str  # مثال: "structure_swing", "order_block", "atr_fallback"
    sl_source_reason: str = ""  # قيمة من SLSource
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExitPlan:
    signal_id: str
    tp1_pct: float = 0.0
    tp1_rr: float = 0.0
    tp2_pct: float = 0.0
    tp2_rr: float = 0.0
    runner_pct: float = 0.0
    move_sl_to_breakeven_after: Optional[str] = None  # "TP1" | None
    trailing_mode: str = ""  # "structure" | "atr" | "range_boundary" | "none"
    time_exit_bars: Optional[int] = None
    time_exit_min_mfe_r: Optional[float] = None
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    signal_id: str
    state: DecisionState
    order_id: Optional[str] = None
    ticket: Optional[int] = None
    retcode: Optional[int] = None
    comment: str = ""
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


@dataclass
class PositionState:
    signal_id: str
    ticket: int
    direction: str
    entry_price: float
    current_sl: float
    volume_remaining: float
    tp1_hit: bool = False
    tp2_hit: bool = False
    breakeven_applied: bool = False
    bars_since_entry: int = 0
    mfe: float = 0.0
    mae: float = 0.0
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShadowOpportunity:
    """[يخص الخطر رقم 7 و8]: shadow_only=True دايمًا صراحة، عشان أي كود
    استهلاك يقدر يفرّق بينها وبين صفقة حقيقية برمجيًا مش بس بالاتفاق
    الضمني. لا تُكتب أبدًا في trades.csv/adaptive_state.json/
    loss_pause_guard.json — هذا القيد مسؤولية نقطة الكتابة الفعلية، مش
    العقد نفسه."""
    signal_id: str
    direction: str
    rejected_reason: str
    entry_price: float
    virtual_sl: float
    virtual_tp1: float
    virtual_tp2: float = 0.0
    mfe: Optional[float] = None
    mae: Optional[float] = None
    tp1_reached: Optional[bool] = None
    tp2_reached: Optional[bool] = None
    sl_reached: Optional[bool] = None
    counterfactual_result: str = ""
    shadow_only: bool = True
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionResult:
    """العقد الجامع — يربط SignalSnapshot بحالة القرار (DecisionState)
    وبأي خطة/رفض مرتبط بيه. ده اللي main.py المفروض يبني بيه القرار
    النهائي بدل قاموس حر."""
    signal: SignalSnapshot
    state: DecisionState
    reason: str = ""
    risk: Optional[RiskDecision] = None
    entry_plan: Optional[FinalEntryPlan] = None
    exit_plan: Optional[ExitPlan] = None
    build_id: str = field(default_factory=lambda: _BUILD_ID or "")
    decision_snapshot_id: str = field(default_factory=new_decision_snapshot_id)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal.to_dict(),
            "state": self.state.value,
            "reason": self.reason,
            "risk": self.risk.to_dict() if self.risk else None,
            "entry_plan": self.entry_plan.to_dict() if self.entry_plan else None,
            "exit_plan": self.exit_plan.to_dict() if self.exit_plan else None,
            "build_id": self.build_id,
            "decision_snapshot_id": self.decision_snapshot_id,
            "created_at": self.created_at,
        }
