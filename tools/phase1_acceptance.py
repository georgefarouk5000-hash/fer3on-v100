# =============================================================================
# FER3ON V3.5 — PHASE-1 ACCEPTANCE RUNNER
# =============================================================================
# Runs the seven Phase-1 acceptance tests as defined in the spec:
#
#   1. Risk Consistency Test            (tests/test_risk_consistency.py)
#   2. Authority Isolation Test         (tests/test_authority_isolation.py)
#   3. Truth Layer Test                 (tests/test_truth_layer.py)
#   4. Micro Stability Test             (tests/test_micro_stability.py)
#   5. SMC Diagnostic Test              (tests/test_smc_diagnostic.py)
#   6. Execution Verification Test      (tests/test_live_execution.py)
#   7. Performance Validation Test      (tests/test_performance_validation.py)
#
# Phase-1 acceptance condition:  كل التعديلات لا تعتمد قبل نجاح السبعة.
# =============================================================================

from __future__ import annotations

import os
import sys
from typing import Any, Dict


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)


def _run_module_test(module_name: str) -> Dict[str, Any]:
    try:
        mod = __import__(module_name, fromlist=["run_all"])
        return mod.run_all()
    except Exception as e:  # hard failure => block release
        return {
            "tests_run": 0,
            "failures": 1,
            "errors": 1,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


def phase1_acceptance() -> Dict[str, Any]:
    plan = [
        ("Risk Consistency",       "tests.test_risk_consistency"),
        ("Authority Isolation",    "tests.test_authority_isolation"),
        ("Truth Layer",            "tests.test_truth_layer"),
        ("Micro Stability",        "tests.test_micro_stability"),
        ("SMC Diagnostic",         "tests.test_smc_diagnostic"),
        ("Execution Verification", "tests.test_live_execution"),
        ("Performance Validation", "tests.test_performance_validation"),
    ]
    results: Dict[str, Any] = {}
    overall_ok = True
    for name, modname in plan:
        r = _run_module_test(modname)
        results[name] = r
        overall_ok = overall_ok and r.get("ok", False)
    results["__OVERALL_OK__"] = overall_ok
    results["__PHASE__"] = "PHASE_1_STABILIZATION"
    return results


def main() -> int:
    import json
    rep = phase1_acceptance()
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if rep.get("__OVERALL_OK__") else 1


if __name__ == "__main__":
    raise SystemExit(main())
