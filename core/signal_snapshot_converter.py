"""
Signal Snapshot Converter - Phase 1A Helper Functions
======================================================

الدور: تحويل dict signals (الطريقة القديمة) إلى SignalSnapshot (الطريقة الجديدة)
دون تغيير أي سلوك حي. هذا ملف helper بحت للتحضير للمرحلة 1B.

[FER3ON-2026-08-31-PHASE1A]
- صفر تغيير على مسار حي
- backward compatible 100%
- كل دالة لها اختبار منفصل
"""

from typing import Any, Dict, Optional
from datetime import datetime, timezone
from core.decision_contracts import SignalSnapshot, DecisionState, DecisionResult
from core.settings import BUILD_ID


def dict_to_signal_snapshot(
    signal_dict: Dict[str, Any],
    strategy: str,
) -> SignalSnapshot:
    """
    تحويل dict قديم إلى SignalSnapshot موحد.
    
    مثال الاستخدام (في المستقبل في main.py):
    ┌─────────────────────────────────────────────────────┐
    │ # الطريقة القديمة (dict):                            │
    │ signal = {                                          │
    │     "direction": "BUY",                             │
    │     "entry_price": 4400.0,                          │
    │     "signal_time": "2026-08-31 09:15:00 UTC",      │
    │     ...                                             │
    │ }                                                   │
    │                                                     │
    │ # الطريقة الجديدة (SignalSnapshot):                 │
    │ snapshot = dict_to_signal_snapshot(signal, "SMC") │
    │ # الآن نقدر نستخدم snapshot.to_dict()             │
    │ # نفس dict القديم، بس مع signal_id + build_id     │
    └─────────────────────────────────────────────────────┘
    
    Args:
        signal_dict: dict signal من strategy runner
        strategy: active strategy name (SMC or DAILY)
    
    Returns:
        SignalSnapshot object
    """
    
    # استخرج القيم الأساسية
    direction = str(signal_dict.get("direction", "")).upper()
    entry_price = float(signal_dict.get("entry_price") or signal_dict.get("price") or 0.0)
    signal_time_raw = signal_dict.get("signal_time") or datetime.now(timezone.utc).isoformat()
    
    # تأكد من format iso للوقت
    if isinstance(signal_time_raw, datetime):
        signal_time = signal_time_raw.isoformat()
    else:
        signal_time = str(signal_time_raw)
    
    # استخرج المعلومات الاختيارية
    regime = str(signal_dict.get("regime", ""))
    session = str(signal_dict.get("session", ""))
    atr = float(signal_dict.get("atr") or 0.0)
    confidence = float(signal_dict.get("confidence") or signal_dict.get("confidence_score") or 0.0)
    quality = float(signal_dict.get("quality") or signal_dict.get("quality_score") or 0.0)
    execution_grade = str(signal_dict.get("execution_grade") or "")
    
    # بنى البيانات المعقدة
    structure = signal_dict.get("structure") or {}
    liquidity = signal_dict.get("liquidity") or {}
    
    # السبب النص
    raw_signal_reason = str(signal_dict.get("reason") or signal_dict.get("raw_signal_reason") or "")
    
    # entry reference (سعر الدخول أو مستوى البنية)
    entry_reference = float(signal_dict.get("entry_reference") or entry_price or 0.0)
    
    return SignalSnapshot(
        signal_id=signal_dict.get("signal_id") or f"sig-{datetime.now(timezone.utc).timestamp()}",
        symbol="XAUUSD",  # الحالي هو XAUUSD فقط
        strategy=strategy.upper(),
        direction=direction,
        signal_time=signal_time,
        entry_reference=entry_reference,
        regime=regime,
        session=session,
        structure=structure,
        liquidity=liquidity,
        atr=atr,
        confidence=confidence,
        quality=quality,
        execution_grade=execution_grade,
        mtf_alignment=str(signal_dict.get("mtf_alignment") or ""),
        raw_signal_reason=raw_signal_reason,
        build_id=BUILD_ID or "",
    )


def decision_result_to_dict(decision: DecisionResult) -> Dict[str, Any]:
    """
    تحويل DecisionResult إلى dict للتوافقية مع الكود القديم.
    
    الفائدة: في المستقبل (Phase 1B)، بدل:
    ┌─────────────────────────────────────────────────┐
    │ if decision.state == DecisionState.APPROVED:   │
    │     execute_trade(...)                         │
    │ else:                                           │
    │     return decision.reason                     │
    └─────────────────────────────────────────────────┘
    
    الطريقة الحالية (backward compatible):
    ┌─────────────────────────────────────────────────┐
    │ decision_dict = decision_result_to_dict(dec)  │
    │ if decision_dict.get("approved"):              │
    │     execute_trade(decision_dict)               │
    │ else:                                           │
    │     return decision_dict.get("reason")        │
    └─────────────────────────────────────────────────┘
    """
    return {
        "signal_id": decision.signal.signal_id,
        "approved": decision.state == DecisionState.APPROVED,
        "state": decision.state.value,
        "reason": decision.reason,
        "build_id": decision.build_id,
        "decision_snapshot_id": decision.decision_snapshot_id,
        "risk": decision.risk.to_dict() if decision.risk else None,
        "entry_plan": decision.entry_plan.to_dict() if decision.entry_plan else None,
        "exit_plan": decision.exit_plan.to_dict() if decision.exit_plan else None,
    }


def validate_signal_snapshot(snapshot: SignalSnapshot) -> tuple[bool, str]:
    """
    تحقق من صحة SignalSnapshot.
    
    Returns:
        (is_valid: bool, reason: str)
    """
    
    # تحقق من الحقول الإلزامية
    if not snapshot.signal_id or not snapshot.signal_id.strip():
        return False, "signal_id is required"
    
    if not snapshot.strategy or snapshot.strategy.upper() not in {"SMC", "DAILY"}:
        return False, f"strategy must be SMC or DAILY, got {snapshot.strategy}"
    
    if not snapshot.direction or snapshot.direction.upper() not in {"BUY", "SELL"}:
        return False, f"direction must be BUY or SELL, got {snapshot.direction}"
    
    if not snapshot.signal_time or not snapshot.signal_time.strip():
        return False, "signal_time is required"
    
    # تحقق من القيم الرقمية
    if snapshot.atr < 0:
        return False, f"atr must be >= 0, got {snapshot.atr}"
    
    if not (0 <= snapshot.confidence <= 100):
        return False, f"confidence must be 0-100, got {snapshot.confidence}"
    
    if not (0 <= snapshot.quality <= 100):
        return False, f"quality must be 0-100, got {snapshot.quality}"
    
    return True, "OK"


if __name__ == "__main__":
    # مثال سريع للاختبار
    test_dict = {
        "signal_id": "test-123",
        "direction": "BUY",
        "entry_price": 4400.0,
        "signal_time": datetime.now(timezone.utc).isoformat(),
        "regime": "TRENDING",
        "session": "LONDON",
        "confidence": 75,
        "quality": 80,
        "atr": 4.5,
    }
    
    snapshot = dict_to_signal_snapshot(test_dict, "SMC")
    print(f"✅ Snapshot created: {snapshot.signal_id}")
    
    is_valid, reason = validate_signal_snapshot(snapshot)
    print(f"✅ Validation: {reason}")
    
    # تحويل للـ dict للتوافقية
    snapshot_dict = snapshot.to_dict()
    print(f"✅ Back to dict: signal_id={snapshot_dict['signal_id']}")
