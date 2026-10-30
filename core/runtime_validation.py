# =========================================
# FER3ON AI V2.2 — RUNTIME VALIDATION
# Generic startup/runtime validation without legacy version branding.
# =========================================

from __future__ import annotations

import importlib
from typing import Any, Dict, List


VALIDATION_TARGETS = {
    "decision_authority": ("core.fer3on_decision_authority", ["build_decision_context", "decide_trade"]),
    "quality_gate": ("core.quality_score", ["evaluate_quality_gate"]),
    "risk_engine": ("core.risk_manager", ["calculate_smart_lot"]),
    "risk_protection": ("core.risk_protection", ["market_is_safe"]),
    "execution_engine": ("core.trade_executor", ["execute_trade"]),
    "memory": ("core.ai_memory", ["store_memory"]),
    "trailing": ("core.trailing_stop", ["update_position_trailing"]),
    "daily_signal": ("core.daily.signal", ["get_daily_signal", "get_daily_bias"]),
}


def run_runtime_validation() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []

    for name, (module_name, required_functions) in VALIDATION_TARGETS.items():
        try:
            module = importlib.import_module(module_name)
            missing = [fn for fn in required_functions if not hasattr(module, fn)]
            passed = not missing
            results.append(
                {
                    "module": name,
                    "module_path": module_name,
                    "passed": passed,
                    "missing": missing,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "module": name,
                    "module_path": module_name,
                    "passed": False,
                    "missing": list(required_functions),
                    "error": str(exc),
                }
            )

    passed_count = sum(1 for item in results if item.get("passed"))
    total = len(results)
    health_score = int(round((passed_count / total) * 100)) if total else 0

    print("[FER3ON AI V2] RUNTIME VALIDATION COMPLETE")
    for result in results:
        status = "PASS" if result.get("passed") else "FAIL"
        print(f"[FER3ON AI V2] {result['module']:<20} {status}")
    print(f"[FER3ON AI V2] HEALTH_SCORE: {health_score}/100")

    return {
        "results": results,
        "summary": {
            "passed": passed_count,
            "total": total,
            "health_score": health_score,
        },
    }
