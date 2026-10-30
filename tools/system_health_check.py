"""System-wide health and compatibility checks for FER3ON."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _module_ok(module_name: str) -> Tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, "ok"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, f"{type(exc).__name__}: {exc}"


def run_health_check() -> Dict[str, Any]:
    """Run a lightweight health assessment and return a score from 0-100."""

    checks: List[Dict[str, Any]] = []
    critical_modules = [
        "core.settings",
        "core.conflict_resolution",
        "brain.master_brain",
        "core.meta_ai_orchestrator",
        "core.v7_integration",
        "core.risk_protection",
        "core.contextual_memory",
        "config.ai_config",
        "config.execution_config",
        "config.risk_config",
    ]

    for module_name in critical_modules:
        ok, detail = _module_ok(module_name)
        checks.append({"name": module_name, "ok": ok, "detail": detail})

    data_dirs = [
        "data",
        "runtime/logs",
        "runtime/state",
        "data/analytics",
        "data/memory",
        "data/history",
        "data/backups",
    ]
    for directory in data_dirs:
        abs_dir = os.path.join(ROOT, directory)
        os.makedirs(abs_dir, exist_ok=True)
        exists = os.path.isdir(abs_dir)
        checks.append({"name": f"dir:{directory}", "ok": exists, "detail": "present" if exists else "missing"})

    try:
        import MetaTrader5 as mt5  # type: ignore
        mt5_available = True
        mt5_detail = "installed"
    except Exception as exc:  # pragma: no cover - optional dependency
        mt5_available = False
        mt5_detail = f"{type(exc).__name__}: {exc}"
    checks.append({"name": "mt5", "ok": mt5_available, "detail": mt5_detail})

    passed = sum(1 for item in checks if item["ok"])
    score = int(round((passed / len(checks)) * 100))

    summary = {
        "passed": passed,
        "total": len(checks),
        "critical_failures": [item["name"] for item in checks if not item["ok"]],
    }

    return {
        "score": score,
        "summary": summary,
        "checks": checks,
    }


def main() -> int:
    result = run_health_check()
    print(f"FER3ON HEALTH SCORE: {result['score']}/100")
    for item in result["checks"]:
        status = "OK" if item["ok"] else "FAIL"
        print(f"[{status}] {item['name']}: {item['detail']}")
    return 0 if result["score"] >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
