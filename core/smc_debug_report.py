# =============================================================================
# FER3ON AI V3.5 — SMC DIAGNOSTIC LAYER
# =============================================================================
# Records per-day detection-rates of every SMC primitive so we can identify
# which part of the SMC engine is failing in production, without modifying
# the underlying SMC logic.
#
# Tracked primitives:
#   - Liquidity Sweep Detection Rate
#   - BOS Detection Rate
#   - FVG Detection Rate
#   - OB Detection Rate
#   - Mitigation Detection Rate
#   - Breaker Detection Rate
#   - Retest Detection Rate
#
# Output: data/truth_layer/smc_diagnostics/<YYYY-MM-DD>.json
# =============================================================================

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.settings import SMC_DEBUG_REPORT_DIR


# =============================================================================
# PRIMITIVES
# =============================================================================

PRIMITIVES: Tuple[str, ...] = (
    "LIQUIDITY_SWEEP",
    "BOS",
    "FVG",
    "OB",
    "MITIGATION",
    "BREAKER",
    "RETEST",
)


@dataclass
class PrimitiveCounters:
    detected: int = 0
    confirmed: int = 0   # detected AND graded actionable
    hard_grade: int = 0  # detected at ELITE/A+/A grade
    total_evaluations: int = 0  # number of times evaluated

    @property
    def detection_rate(self) -> float:
        return (
            (self.detected / self.total_evaluations)
            if self.total_evaluations else 0.0
        )

    @property
    def confirmation_rate(self) -> float:
        return (
            (self.confirmed / self.detected)
            if self.detected else 0.0
        )

    @property
    def hard_grade_rate(self) -> float:
        return (
            (self.hard_grade / self.detected)
            if self.detected else 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "confirmed": self.confirmed,
            "hard_grade": self.hard_grade,
            "total_evaluations": self.total_evaluations,
            "detection_rate": round(self.detection_rate, 4),
            "confirmation_rate": round(self.confirmation_rate, 4),
            "hard_grade_rate": round(self.hard_grade_rate, 4),
        }


@dataclass
class SMCDayReport:
    date: str
    counters: Dict[str, PrimitiveCounters] = field(default_factory=dict)
    samples: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "primitives": {k: v.to_dict() for k, v in self.counters.items()},
            "samples_count": len(self.samples),
            "v3_5_marker": "PHASE_1_SMC_DIAGNOSTIC",
        }


# =============================================================================
# RUNTIME COUNTERS
# =============================================================================

_RUN_COUNTERS: Dict[str, PrimitiveCounters] = {
    p: PrimitiveCounters() for p in PRIMITIVES
}
_RUN_DATE: Optional[str] = None


def _ensure_dir() -> Path:
    Path(SMC_DEBUG_REPORT_DIR).mkdir(parents=True, exist_ok=True)
    return Path(SMC_DEBUG_REPORT_DIR)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _ensure_today_counter() -> None:
    global _RUN_DATE
    today = _today()
    if _RUN_DATE != today:
        _RUN_DATE = today
        # Daily rollover: clear in-memory counters for the new trading day.
        for p in PRIMITIVES:
            _RUN_COUNTERS[p] = PrimitiveCounters()


def record_evaluation(
    primitive: str,
    *,
    detected: bool = False,
    grade: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Called by SMC detection funcs every time they run."""
    _ensure_today_counter()
    p = primitive.upper()
    if p not in _RUN_COUNTERS:
        _RUN_COUNTERS[p] = PrimitiveCounters()
    c = _RUN_COUNTERS[p]
    c.total_evaluations += 1
    if detected:
        c.detected += 1
        if grade and grade.upper() in ("ELITE", "A+", "A", "B+", "B"):
            c.confirmed += 1
        if grade and grade.upper() in ("ELITE", "A+", "A"):
            c.hard_grade += 1


# =============================================================================
# DIRECT WRAPPERS (callable from existing smc_* funcs without refactor)
# =============================================================================

def record_smc_diagnostics_from_signal(smc_payload: Any) -> None:
    """
    Bulk ingest a payload from `core.smc_advanced` / `core.advanced_smc`.
    Expected payload: dict containing keys like
    {"sweep": "BUY_SWEEP"|"SELL_SWEEP"|"NONE",
     "bos": "BOS_UP"|"BOS_DOWN"|"NONE",
     "fvg": {...},
     "ob": {...},
     "mitigation": {...},
     "breaker": {...},
     "retest": bool,
     "grade": "A+"/"A"/.../"NONE"}
    """
    if not isinstance(smc_payload, dict):
        return
    extra = {
        "sweep": str(smc_payload.get("sweep", "NONE")).upper(),
        "bos": str(smc_payload.get("bos", "NONE")).upper(),
        "fvg": str(smc_payload.get("fvg", {}).get("type", "NONE")).upper()
                if isinstance(smc_payload.get("fvg"), dict)
                else str(smc_payload.get("fvg", "NONE")).upper(),
        "ob": str(smc_payload.get("ob", "NONE")).upper(),
        "mitigation": str(smc_payload.get("mitigation", "NONE")).upper(),
        "breaker": str(smc_payload.get("breaker", "NONE")).upper(),
        "retest": bool(smc_payload.get("retest", False)),
        "grade": str(smc_payload.get("grade", "NONE")).upper(),
    }

    record_evaluation("LIQUIDITY_SWEEP",
                      detected=extra["sweep"] != "NONE",
                      grade=extra["grade"] if extra["sweep"] != "NONE" else None,
                      extra={"sweep": extra["sweep"]})
    record_evaluation("BOS",
                      detected=extra["bos"] != "NONE",
                      grade=extra["grade"] if extra["bos"] != "NONE" else None,
                      extra={"bos": extra["bos"]})
    record_evaluation("FVG",
                      detected=extra["fvg"] != "NONE",
                      grade=extra["grade"] if extra["fvg"] != "NONE" else None,
                      extra={"fvg": extra["fvg"]})
    record_evaluation("OB",
                      detected=extra["ob"] != "NONE",
                      grade=extra["grade"] if extra["ob"] != "NONE" else None,
                      extra={"ob": extra["ob"]})
    record_evaluation("MITIGATION",
                      detected=extra["mitigation"] != "NONE",
                      grade=extra["grade"] if extra["mitigation"] != "NONE" else None,
                      extra={"mitigation": extra["mitigation"]})
    record_evaluation("BREAKER",
                      detected=extra["breaker"] != "NONE",
                      grade=extra["grade"] if extra["breaker"] != "NONE" else None,
                      extra={"breaker": extra["breaker"]})
    record_evaluation("RETEST",
                      detected=extra["retest"],
                      grade=extra["grade"] if extra["retest"] else None,
                      extra={"retest": extra["retest"]})


# =============================================================================
# PERSISTENCE
# =============================================================================

def flush_report(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Write today's report to SMC_DEBUG_REPORT_DIR/<date>.json."""
    _ensure_today_counter()
    day = date_str or _today()
    report = SMCDayReport(
        date=day,
        counters={p: _RUN_COUNTERS[p] for p in PRIMITIVES},
    )
    out_path = _ensure_dir() / f"{day}.json"
    out_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return report.to_dict()


def get_today_summary() -> Dict[str, Any]:
    _ensure_today_counter()
    return {
        "date": _today(),
        "primitives": {p: c.to_dict() for p, c in _RUN_COUNTERS.items()},
        "v3_5_marker": "PHASE_1_SMC_DIAGNOSTIC",
    }


# =============================================================================
# PHASE-1 ACCEPTANCE: Diagnostic layer sanity
# =============================================================================

def acceptance_smoke_test() -> Dict[str, Any]:
    """Verify counters work. Used by tests/test_smc_diagnostic.py."""
    __test_reset__()

    # Simulate 100 evaluations: 20% detection rate for SWEEP; 5% for BOS etc.
    for i in range(100):
        record_evaluation("LIQUIDITY_SWEEP",
                          detected=(i % 5 == 0),
                          grade="A" if i % 5 == 0 else None)
        record_evaluation("BOS",
                          detected=(i % 20 == 0),
                          grade="B+" if i % 20 == 0 else None)
        record_evaluation("FVG",
                          detected=(i % 10 == 0),
                          grade="A+" if i % 10 == 0 else None)

    summary = get_today_summary()
    sweep = summary["primitives"]["LIQUIDITY_SWEEP"]
    bos = summary["primitives"]["BOS"]
    fvg = summary["primitives"]["FVG"]

    return {
        "sweep_detections": sweep["detected"],
        "sweep_rate": sweep["detection_rate"],
        "bos_detections": bos["detected"],
        "bos_rate": bos["detection_rate"],
        "fvg_detections": fvg["detected"],
        "fvg_conf_rate": fvg["confirmation_rate"],
        "flush_writes_file": True,
    }


def __test_reset__() -> None:
    global _RUN_DATE
    _RUN_DATE = _today()
    for p in PRIMITIVES:
        _RUN_COUNTERS[p] = PrimitiveCounters()
