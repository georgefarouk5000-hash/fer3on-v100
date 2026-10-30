# =========================================
# FER3ON V7 — STARTUP AUDIT
# Deep functional validation for V7 modules
# =========================================

from __future__ import annotations

from typing import Any, Dict

from core.v7_validator import run_v7_deep_validation


def run_v7_audit() -> Dict[str, Any]:
    report = run_v7_deep_validation()
    print("[V7 AUDIT] STARTUP VALIDATION COMPLETE")
    for result in report["results"]:
        status = "PASS" if result.get("passed") else "FAIL"
        print(f"[V7 AUDIT] {result['module']:<20} {status}")
    print(f"[V7 AUDIT] HEALTH_SCORE: {report['summary']['health_score']}/100")
    return {"results": report["results"], "summary": report["summary"]}
