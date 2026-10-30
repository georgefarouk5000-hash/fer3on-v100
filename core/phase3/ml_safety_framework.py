# =============================================================================
# FER3ON — PHASE 3 | ML_SAFETY_FRAMEWORK (Shadow Mode)
# =============================================================================
# الدور: مراقبة صحة نماذج ML وكشف الانجراف.
# الوضع الحالي: SHADOW ONLY — مراقب ومقيّم ومنبّه فقط.
#
# المكوّنات:
#   - Drift Detection: كشف انجراف النموذج عن الأداء الأساسي
#   - Model Health Score: درجة صحة النموذج (0-100)
#   - Retraining Recommendation: توصية بإعادة التدريب
#   - Feature Stability: استقرار المدخلات
#
# ما لا يفعله:
#   - لا يحجب صفقات (ML_SAFETY_LIVE_BLOCK=False)
#   - لا يُلغي قرارات تنفيذية
#   - لا يغيّر أي قيمة runtime
# =============================================================================

from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from core.settings import (
    ML_SAFETY_DRIFT_THRESHOLD,
    ML_SAFETY_ENABLED,
    ML_SAFETY_HEALTH_ALERT_BELOW,
    ML_SAFETY_HEALTH_WARN_BELOW,
    ML_SAFETY_LIVE_BLOCK,
    ML_SAFETY_RECHECK_INTERVAL,
    ML_SAFETY_RETRAIN_RECOMMEND_AT,
    ML_SAFETY_SHADOW_LOG,
    PHASE3_ML_SAFETY_DIR,
)

_STATE_FILE = os.path.join(PHASE3_ML_SAFETY_DIR, "ml_safety_state.json")
_SHADOW_LOG_FILE = os.path.join(PHASE3_ML_SAFETY_DIR, "ml_safety_shadow.jsonl")
_ALERT_LOG_FILE = os.path.join(PHASE3_ML_SAFETY_DIR, "ml_safety_alerts.jsonl")

assert not ML_SAFETY_LIVE_BLOCK, (
    "ML_SAFETY: Live blocking is disabled in Phase 3. "
    "Framework operates in advisory/monitoring mode only."
)

# نافذة متدحرجة لتتبع أداء النموذج
_PREDICTION_WINDOW: Deque[Dict[str, Any]] = deque(maxlen=100)
_last_health_check: float = 0.0


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MLPredictionRecord:
    """سجل تنبؤ نموذج ML مع النتيجة الفعلية."""
    prediction_score: float = 0.0    # تنبؤ النموذج (0-100)
    actual_outcome: Optional[bool] = None  # None=لم تُغلق بعد، True=ربح، False=خسارة
    strategy: str = "UNKNOWN"
    session: str = "UNKNOWN"
    regime: str = "UNKNOWN"
    timestamp: float = field(default_factory=time.time)


@dataclass
class MLHealthReport:
    """تقرير صحة ML."""
    health_score: float = 50.0
    drift_detected: bool = False
    drift_magnitude: float = 0.0
    health_status: str = "UNKNOWN"  # HEALTHY / WARNING / ALERT / CRITICAL
    prediction_accuracy: float = 0.0
    calibration_error: float = 0.0
    sample_size: int = 0
    retrain_recommended: bool = False
    retrain_reason: str = ""
    warnings: List[str] = field(default_factory=list)
    mode: str = "SHADOW"
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# HEALTH COMPUTATION
# =============================================================================

def _ensure_dirs() -> None:
    os.makedirs(PHASE3_ML_SAFETY_DIR, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    _ensure_dirs()
    default = {
        "version": "phase3.0",
        "total_predictions": 0,
        "total_resolved": 0,
        "correct_predictions": 0,
        "last_health_score": 50.0,
        "last_drift_magnitude": 0.0,
        "drift_alerts_count": 0,
        "retrain_recommendations": 0,
        "last_check": 0.0,
        "baseline_accuracy": None,
        "prediction_history": [],
    }
    if not os.path.exists(_STATE_FILE):
        return default
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**default, **data}
    except Exception:
        return default


def _save_state(state: Dict[str, Any]) -> None:
    state["last_check"] = time.time()
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ML_SAFETY] State save error: {e}")


def _compute_prediction_accuracy(resolved_records: List[Dict[str, Any]]) -> float:
    """حساب دقة التنبؤات على السجلات المحلولة."""
    if not resolved_records:
        return 0.0
    correct = sum(
        1 for r in resolved_records
        if r.get("actual_outcome") is not None and (
            (r["prediction_score"] > 60 and r["actual_outcome"] is True) or
            (r["prediction_score"] <= 60 and r["actual_outcome"] is False)
        )
    )
    return round(correct / len(resolved_records), 4)


def _compute_drift_magnitude(
    current_accuracy: float,
    baseline_accuracy: Optional[float],
) -> float:
    """حساب حجم الانجراف عن الخط الأساسي."""
    if baseline_accuracy is None or baseline_accuracy == 0:
        return 0.0
    drift = abs(current_accuracy - baseline_accuracy) / max(0.001, baseline_accuracy)
    return round(drift, 4)


def _compute_calibration_error(records: List[Dict[str, Any]]) -> float:
    """
    Expected Calibration Error (ECE) المبسَّط.
    يقيس مدى توافق ثقة النموذج مع دقته الفعلية.
    """
    if len(records) < 10:
        return 0.0

    buckets = {i: {"total": 0, "correct": 0, "confidence_sum": 0.0}
               for i in range(10)}

    for r in records:
        if r.get("actual_outcome") is None:
            continue
        score = r.get("prediction_score", 50.0) / 100.0
        bucket_idx = min(9, int(score * 10))
        buckets[bucket_idx]["total"] += 1
        buckets[bucket_idx]["confidence_sum"] += score
        if (score > 0.6 and r["actual_outcome"]) or (score <= 0.6 and not r["actual_outcome"]):
            buckets[bucket_idx]["correct"] += 1

    ece = 0.0
    total = sum(b["total"] for b in buckets.values())
    if total == 0:
        return 0.0

    for bucket in buckets.values():
        n = bucket["total"]
        if n == 0:
            continue
        accuracy = bucket["correct"] / n
        avg_confidence = bucket["confidence_sum"] / n
        ece += (n / total) * abs(avg_confidence - accuracy)

    return round(ece, 4)


def _compute_health_score(
    prediction_accuracy: float,
    drift_magnitude: float,
    calibration_error: float,
    sample_size: int,
) -> float:
    """درجة صحة النموذج المركّبة (0-100)."""
    if sample_size < 10:
        return 50.0  # لا بيانات كافية — محايد

    # 1) دقة التنبؤ (50% من الوزن)
    accuracy_score = prediction_accuracy * 100 * 0.50

    # 2) عدم الانجراف (30% من الوزن)
    drift_penalty = min(30.0, drift_magnitude * 100)
    drift_score = max(0, 30.0 - drift_penalty)

    # 3) معايرة جيدة (20% من الوزن)
    calibration_penalty = min(20.0, calibration_error * 100)
    calibration_score = max(0, 20.0 - calibration_penalty)

    health = accuracy_score + drift_score + calibration_score
    return round(min(100.0, max(0.0, health)), 2)


def _determine_health_status(health_score: float) -> str:
    if health_score >= ML_SAFETY_HEALTH_WARN_BELOW:
        return "HEALTHY"
    elif health_score >= ML_SAFETY_HEALTH_ALERT_BELOW:
        return "WARNING"
    elif health_score >= 20.0:
        return "ALERT"
    else:
        return "CRITICAL"


# =============================================================================
# PUBLIC API
# =============================================================================

def record_ml_prediction(
    prediction_score: float,
    strategy: str = "UNKNOWN",
    session: str = "UNKNOWN",
    regime: str = "UNKNOWN",
) -> None:
    """يُسجّل تنبؤ ML للمراقبة لاحقاً."""
    if not ML_SAFETY_ENABLED:
        return

    record = {
        "prediction_score": prediction_score,
        "actual_outcome": None,
        "strategy": strategy,
        "session": session,
        "regime": regime,
        "timestamp": time.time(),
    }
    _PREDICTION_WINDOW.append(record)

    state = _load_state()
    state["total_predictions"] = state.get("total_predictions", 0) + 1
    # حفظ آخر 200 تنبؤ في الحالة
    history = state.get("prediction_history", [])
    history.append(record)
    if len(history) > 200:
        history = history[-200:]
    state["prediction_history"] = history
    _save_state(state)


def resolve_ml_prediction(
    timestamp: float,
    was_winner: bool,
) -> None:
    """يُحدّث نتيجة تنبؤ سابق بعد إغلاق الصفقة."""
    if not ML_SAFETY_ENABLED:
        return

    # تحديث في النافذة المتدحرجة
    for record in _PREDICTION_WINDOW:
        if abs(record["timestamp"] - timestamp) < 1.0 and record["actual_outcome"] is None:
            record["actual_outcome"] = was_winner
            break

    state = _load_state()
    state["total_resolved"] = state.get("total_resolved", 0) + 1
    if was_winner:
        state["correct_predictions"] = state.get("correct_predictions", 0) + 1

    # تحديث baseline إذا كانت أول 50 صفقة
    if state.get("baseline_accuracy") is None and state["total_resolved"] >= 50:
        resolved = [r for r in _PREDICTION_WINDOW if r.get("actual_outcome") is not None]
        state["baseline_accuracy"] = _compute_prediction_accuracy(resolved)
        print(f"[ML_SAFETY] Baseline accuracy set: {state['baseline_accuracy']:.4f}")

    _save_state(state)


def run_health_check() -> MLHealthReport:
    """
    تشغيل فحص صحة شامل لنماذج ML.
    يُستدعى دورياً — لا يُوقف أي تنفيذ.
    """
    global _last_health_check

    if not ML_SAFETY_ENABLED:
        return MLHealthReport(health_status="DISABLED", mode="DISABLED")

    state = _load_state()
    resolved = [r for r in _PREDICTION_WINDOW if r.get("actual_outcome") is not None]
    sample_size = len(resolved)

    prediction_accuracy = _compute_prediction_accuracy(resolved)
    baseline_accuracy = state.get("baseline_accuracy")
    drift_magnitude = _compute_drift_magnitude(prediction_accuracy, baseline_accuracy)
    calibration_error = _compute_calibration_error(resolved)
    health_score = _compute_health_score(
        prediction_accuracy, drift_magnitude, calibration_error, sample_size
    )
    health_status = _determine_health_status(health_score)

    drift_detected = drift_magnitude > ML_SAFETY_DRIFT_THRESHOLD

    warnings = []
    if health_score < ML_SAFETY_HEALTH_WARN_BELOW:
        warnings.append(f"Model health degraded: {health_score:.1f} < {ML_SAFETY_HEALTH_WARN_BELOW}")
    if drift_detected:
        warnings.append(f"Model drift detected: {drift_magnitude:.3f} > {ML_SAFETY_DRIFT_THRESHOLD}")
        state["drift_alerts_count"] = state.get("drift_alerts_count", 0) + 1
    if calibration_error > 0.15:
        warnings.append(f"High calibration error: {calibration_error:.3f}")

    # توصية بإعادة التدريب
    retrain_recommended = False
    retrain_reason = ""
    total_trades = state.get("total_resolved", 0)
    if total_trades > 0 and total_trades % ML_SAFETY_RETRAIN_RECOMMEND_AT == 0:
        retrain_recommended = True
        retrain_reason = f"Periodic retraining at {total_trades} trades"
    elif drift_detected and drift_magnitude > ML_SAFETY_DRIFT_THRESHOLD * 2:
        retrain_recommended = True
        retrain_reason = f"Severe drift detected: {drift_magnitude:.3f}"
        state["retrain_recommendations"] = state.get("retrain_recommendations", 0) + 1

    state["last_health_score"] = health_score
    state["last_drift_magnitude"] = drift_magnitude
    _save_state(state)
    _last_health_check = time.time()

    report = MLHealthReport(
        health_score=health_score,
        drift_detected=drift_detected,
        drift_magnitude=drift_magnitude,
        health_status=health_status,
        prediction_accuracy=prediction_accuracy,
        calibration_error=calibration_error,
        sample_size=sample_size,
        retrain_recommended=retrain_recommended,
        retrain_reason=retrain_reason,
        warnings=warnings,
        mode="SHADOW",
    )

    # تسجيل
    if ML_SAFETY_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "report": asdict(report),
        }
        log_file = _ALERT_LOG_FILE if warnings else _SHADOW_LOG_FILE
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ML_SAFETY] Log error: {e}")

    for w in warnings:
        print(f"[ML_SAFETY ⚠] {w}")

    print(
        f"[ML_SAFETY SHADOW] Health={health_score:.1f} ({health_status}) | "
        f"Accuracy={prediction_accuracy:.3f} | Drift={drift_magnitude:.3f} | "
        f"Sample={sample_size} | Retrain={retrain_recommended}"
    )

    return report


def should_run_health_check() -> bool:
    """هل حان وقت فحص الصحة الدوري؟"""
    return (time.time() - _last_health_check) >= ML_SAFETY_RECHECK_INTERVAL


def get_ml_safety_status() -> Dict[str, Any]:
    """تقرير حالة ML_SAFETY_FRAMEWORK."""
    state = _load_state()
    return {
        "component": "ML_SAFETY_FRAMEWORK",
        "mode": "SHADOW",
        "enabled": ML_SAFETY_ENABLED,
        "live_block": ML_SAFETY_LIVE_BLOCK,
        "last_health_score": state.get("last_health_score", 50.0),
        "total_predictions": state.get("total_predictions", 0),
        "total_resolved": state.get("total_resolved", 0),
        "drift_alerts_count": state.get("drift_alerts_count", 0),
        "retrain_recommendations": state.get("retrain_recommendations", 0),
        "baseline_accuracy": state.get("baseline_accuracy"),
    }
