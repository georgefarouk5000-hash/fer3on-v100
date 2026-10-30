# =============================================================================
# FER3ON — PHASE 3 | SYSTEM_HEALTH_LAYER (Shadow Mode)
# =============================================================================
# الدور: مراقبة الصحة الموحّدة للنظام (Phase 3 Components + Core).
# الوضع الحالي: SHADOW ONLY — مراقبة وتنبيه فقط.
#
# يجمع مؤشرات صحة من:
#   - FINAL_BRAIN shadow cycles
#   - PORTFOLIO_BRAIN exposure
#   - ML_SAFETY health score
#   - STRATEGY_DNA rankings
#   - Core runtime status
#
# لا يُوقف أي عملية — فقط يُقيّم ويُنبّه.
# =============================================================================

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    PHASE3_SYSTEM_HEALTH_DIR,
    SYSTEM_HEALTH_ALERT_SCORE,
    SYSTEM_HEALTH_CHECK_INTERVAL,
    SYSTEM_HEALTH_CRITICAL_SCORE,
    SYSTEM_HEALTH_ENABLED,
    SYSTEM_HEALTH_SHADOW_LOG,
    SYSTEM_HEALTH_WARN_SCORE,
)

_STATE_FILE = os.path.join(PHASE3_SYSTEM_HEALTH_DIR, "system_health_state.json")
_SHADOW_LOG_FILE = os.path.join(PHASE3_SYSTEM_HEALTH_DIR, "system_health_shadow.jsonl")

_last_check_time: float = 0.0


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ComponentHealth:
    """صحة مكوّن واحد."""
    component_name: str = "UNKNOWN"
    health_score: float = 50.0
    status: str = "UNKNOWN"       # OK / WARNING / ALERT / CRITICAL / DISABLED
    last_seen: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealthReport:
    """تقرير الصحة الموحَّد."""
    overall_score: float = 50.0
    overall_status: str = "UNKNOWN"
    components: List[ComponentHealth] = field(default_factory=list)
    active_warnings: List[str] = field(default_factory=list)
    active_alerts: List[str] = field(default_factory=list)
    phase3_readiness: float = 0.0
    mode: str = "SHADOW"
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# HEALTH AGGREGATION
# =============================================================================

def _ensure_dirs() -> None:
    os.makedirs(PHASE3_SYSTEM_HEALTH_DIR, exist_ok=True)


def _score_to_status(score: float) -> str:
    if score >= SYSTEM_HEALTH_WARN_SCORE:
        return "OK"
    elif score >= SYSTEM_HEALTH_ALERT_SCORE:
        return "WARNING"
    elif score >= SYSTEM_HEALTH_CRITICAL_SCORE:
        return "ALERT"
    else:
        return "CRITICAL"


def _collect_phase3_component_health() -> List[ComponentHealth]:
    """يجمع صحة مكوّنات Phase 3."""
    components = []

    # FINAL_BRAIN
    try:
        from core.phase3.final_brain import get_readiness_report
        report = get_readiness_report()
        readiness = report.get("readiness_score", 0.0)
        components.append(ComponentHealth(
            component_name="FINAL_BRAIN",
            health_score=readiness,
            status=_score_to_status(readiness),
            last_seen=time.time(),
            details={
                "shadow_cycles": report.get("total_shadow_cycles", 0),
                "accuracy": report.get("approval_accuracy", 0.0),
                "false_reject_rate": report.get("false_rejection_rate", 0.0),
            },
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="FINAL_BRAIN",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    # PORTFOLIO_BRAIN
    try:
        from core.phase3.portfolio_brain import get_portfolio_brain_status
        status = get_portfolio_brain_status()
        enabled_score = 80.0 if status.get("enabled") else 0.0
        components.append(ComponentHealth(
            component_name="PORTFOLIO_BRAIN",
            health_score=enabled_score,
            status="OK" if status.get("enabled") else "DISABLED",
            last_seen=time.time(),
            details=status,
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="PORTFOLIO_BRAIN",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    # ML_SAFETY
    try:
        from core.phase3.ml_safety_framework import get_ml_safety_status
        status = get_ml_safety_status()
        ml_score = status.get("last_health_score", 50.0)
        components.append(ComponentHealth(
            component_name="ML_SAFETY",
            health_score=ml_score,
            status=_score_to_status(ml_score),
            last_seen=time.time(),
            details=status,
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="ML_SAFETY",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    # STRATEGY_DNA
    try:
        from core.phase3.strategy_dna import get_strategy_dna_status
        status = get_strategy_dna_status()
        tracked = status.get("strategies_tracked", 0)
        dna_score = min(100.0, tracked * 20.0)  # 5 استراتيجيات = 100
        components.append(ComponentHealth(
            component_name="STRATEGY_DNA",
            health_score=dna_score,
            status="OK" if tracked >= 3 else ("WARNING" if tracked >= 1 else "SPARSE"),
            last_seen=time.time(),
            details={"strategies_tracked": tracked, "total_updates": status.get("total_updates", 0)},
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="STRATEGY_DNA",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    # GOLD_CONTEXT
    try:
        from core.phase3.gold_context_layer import get_gold_context_status
        status = get_gold_context_status()
        gold_score = 75.0 if status.get("enabled") else 0.0
        components.append(ComponentHealth(
            component_name="GOLD_CONTEXT",
            health_score=gold_score,
            status="OK" if status.get("enabled") else "DISABLED",
            last_seen=time.time(),
            details={"live_influence": status.get("live_influence", False)},
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="GOLD_CONTEXT",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    return components


def _collect_core_health() -> List[ComponentHealth]:
    """يجمع صحة مكوّنات Core الأساسية."""
    components = []

    # Portfolio Risk Authority
    try:
        from core.settings import PORTFOLIO_RISK_AUTHORITY_ACTIVE
        score = 90.0 if PORTFOLIO_RISK_AUTHORITY_ACTIVE else 50.0
        components.append(ComponentHealth(
            component_name="PORTFOLIO_RISK_AUTHORITY",
            health_score=score,
            status="OK" if PORTFOLIO_RISK_AUTHORITY_ACTIVE else "WARNING",
            last_seen=time.time(),
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="PORTFOLIO_RISK_AUTHORITY",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    # Adaptive Learning (Shadow Mode Check)
    try:
        from core.settings import ADAPTIVE_SHADOW_ONLY
        score = 80.0 if ADAPTIVE_SHADOW_ONLY else 50.0
        status_str = "OK" if ADAPTIVE_SHADOW_ONLY else "LIVE_ACTIVE"
        components.append(ComponentHealth(
            component_name="ADAPTIVE_LEARNING",
            health_score=score,
            status=status_str,
            last_seen=time.time(),
            details={"shadow_only": ADAPTIVE_SHADOW_ONLY},
        ))
    except Exception as e:
        components.append(ComponentHealth(
            component_name="ADAPTIVE_LEARNING",
            health_score=0.0,
            status="ERROR",
            details={"error": str(e)},
        ))

    return components


# =============================================================================
# PUBLIC API
# =============================================================================

def run_system_health_check() -> SystemHealthReport:
    """
    فحص شامل لصحة النظام.
    يُستدعى دورياً — لا يُوقف أي عملية.
    """
    global _last_check_time

    if not SYSTEM_HEALTH_ENABLED:
        return SystemHealthReport(overall_status="DISABLED", mode="DISABLED")

    phase3_components = _collect_phase3_component_health()
    core_components = _collect_core_health()
    all_components = phase3_components + core_components

    # حساب الدرجة الكلية (متوسط مرجّح)
    if all_components:
        total_score = sum(c.health_score for c in all_components) / len(all_components)
    else:
        total_score = 50.0

    overall_score = round(total_score, 2)
    overall_status = _score_to_status(overall_score)

    # جمع التحذيرات والإنذارات
    warnings = []
    alerts = []
    for comp in all_components:
        if comp.status == "WARNING":
            warnings.append(f"{comp.component_name}: {comp.status} ({comp.health_score:.0f})")
        elif comp.status in ("ALERT", "CRITICAL", "ERROR"):
            alerts.append(f"{comp.component_name}: {comp.status} ({comp.health_score:.0f})")

    # حساب جاهزية Phase 3
    phase3_readiness = _compute_phase3_readiness(phase3_components)

    report = SystemHealthReport(
        overall_score=overall_score,
        overall_status=overall_status,
        components=all_components,
        active_warnings=warnings,
        active_alerts=alerts,
        phase3_readiness=phase3_readiness,
        mode="SHADOW",
    )

    # تسجيل
    if SYSTEM_HEALTH_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "overall_score": overall_score,
            "overall_status": overall_status,
            "phase3_readiness": phase3_readiness,
            "warnings": warnings,
            "alerts": alerts,
            "components": [asdict(c) for c in all_components],
        }
        try:
            with open(_SHADOW_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[SYSTEM_HEALTH] Log error: {e}")

    _last_check_time = time.time()

    if alerts:
        print(f"[SYSTEM_HEALTH 🔴 ALERT] Overall={overall_score:.1f} | Alerts: {' | '.join(alerts)}")
    elif warnings:
        print(f"[SYSTEM_HEALTH ⚠ WARNING] Overall={overall_score:.1f} | Warnings: {' | '.join(warnings)}")
    else:
        print(
            f"[SYSTEM_HEALTH ✓] Overall={overall_score:.1f} ({overall_status}) | "
            f"Phase3 Readiness={phase3_readiness:.1f}% | Components={len(all_components)}"
        )

    return report


def _compute_phase3_readiness(phase3_components: List[ComponentHealth]) -> float:
    """يحسب نسبة جاهزية Phase 3 بناءً على أداء المكوّنات."""
    if not phase3_components:
        return 0.0

    ok_count = sum(1 for c in phase3_components if c.status in ("OK", "DISABLED"))
    total = len(phase3_components)
    base_readiness = (ok_count / total) * 100.0

    # مكافأة إذا كانت FINAL_BRAIN تعمل بشكل جيد
    final_brain = next(
        (c for c in phase3_components if c.component_name == "FINAL_BRAIN"), None
    )
    if final_brain and final_brain.health_score >= 70:
        base_readiness = min(100.0, base_readiness + 10.0)

    return round(base_readiness, 2)


def should_run_health_check() -> bool:
    """هل حان وقت الفحص الدوري؟"""
    return (time.time() - _last_check_time) >= SYSTEM_HEALTH_CHECK_INTERVAL


def get_system_health_summary() -> Dict[str, Any]:
    """ملخص سريع لصحة النظام."""
    try:
        report = run_system_health_check()
        return {
            "overall_score": report.overall_score,
            "overall_status": report.overall_status,
            "phase3_readiness": report.phase3_readiness,
            "warnings_count": len(report.active_warnings),
            "alerts_count": len(report.active_alerts),
            "component_count": len(report.components),
        }
    except Exception as e:
        return {"error": str(e), "overall_status": "ERROR"}
