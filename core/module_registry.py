import importlib
from typing import Any, Dict


MODULE_SPECS = {
    "settings": ("core.settings", True),
    "ai_memory": ("core.ai_memory", True),
    "trade_dna": ("brain.trade_dna", True),
    "ml": ("ml.ml_orchestrator", True),
    "ml_manager": ("ml.ml_manager", True),
    "telegram": ("core.telegram_bot", True),
    "risk_engine": ("core.risk_manager", True),
    "decision_authority": ("core.fer3on_decision_authority", True),
    "smc_engine": ("core.smc_entry_engine", True),
    "daily_engine": ("core.daily.signal", True),
    "execution_engine": ("core.trade_executor", True),
    "execution_optimizer": ("core.execution_optimizer_v2", True),
    "session_intelligence": ("core.session_intelligence", True),
    "unified_decision": ("core.unified_decision", True),
    "watchdog": ("core.watchdog", True),
    "certification": ("certification.framework", True),
    "database": ("core.data_integrity", True),
    "analytics": ("core.analytics", True),
}


def build_module_registry() -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}
    for name, (module_name, enabled) in MODULE_SPECS.items():
        status = "DISABLED" if not enabled else "ACTIVE"
        details: Dict[str, Any] = {"status": status, "module": module_name, "enabled": enabled}
        if enabled:
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # pragma: no cover - defensive fallback
                details["status"] = "ERROR"
                details["error"] = str(exc)
        registry[name] = details
    return registry


def build_runtime_state() -> Dict[str, Any]:
    registry = build_module_registry()
    errors = [name for name, info in registry.items() if info.get("status") == "ERROR"]
    disabled = [name for name, info in registry.items() if info.get("status") == "DISABLED"]
    return {
        "module_registry": registry,
        "status": "SYSTEM_BLOCKED" if errors else "SYSTEM_READY",
        "errors": errors,
        "disabled": disabled,
    }
