# =========================================
# FER3ON AI V2.2 — STARTUP CHECK
# Startup integrity validation before live loop
# =========================================

import importlib
from pathlib import Path

from core.settings import ANALYTICS_DIR, BACKUP_DIR, HISTORY_DIR, LOGS_DIR, MEMORY_DIR
from core.runtime_validation import run_runtime_validation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = DATA_DIR / "models"
REQUIRED_DIRS = [LOGS_DIR, ANALYTICS_DIR, MEMORY_DIR, HISTORY_DIR, BACKUP_DIR, "data/models"]
RECOMMENDED_FILES = [
    "config.env",
    "requirements.txt",
    "data/history/trades.csv",
    "data/memory/ai_memory.csv",
    "data/trade_dna_v2.json",
]
OPTIONAL_MODEL_FILES = [
    "data/models/xgb_model_sklearn.pkl",
    "data/models/nn_model.pkl",
    "data/models/xgb_scaler_sklearn.pkl",
]
MODULE_REGISTRY = {
    "settings": "core.settings",
    "ai_memory": "core.ai_memory",
    "trade_dna": "brain.trade_dna",
    "ml": "ml.ml_orchestrator",
    "telegram": "core.telegram_bot",
    "risk_engine": "core.risk_manager",
    "smc_engine": "core.smc_entry_engine",
    "daily_engine": "core.daily.signal",
    "execution_engine": "core.trade_executor",
    "execution_optimizer": "core.execution_optimizer_v2",
    "session_intelligence": "core.session_intelligence",
    "unified_decision": "core.unified_decision",
    "watchdog": "core.watchdog",
    "database": "core.data_integrity",
    "analytics": "core.analytics",
}
CRITICAL_FUNCTIONS = {
    "core.fer3on_decision_authority": ["build_decision_context", "decide_trade"],
    "core.risk_manager": ["calculate_smart_lot"],
    "core.risk_protection": ["market_is_safe"],
    "core.confidence_engine": ["get_strategy_confidence"],
    "core.trailing_stop": ["update_position_trailing"],
    "core.trade_executor": ["execute_trade"],
    "brain.trade_dna": ["record_trade_dna"],
    "core.ai_memory": ["store_memory"],
}


def _path_exists(rel_path):
    return (PROJECT_ROOT / rel_path).exists()


def _ensure_dir(rel_path):
    path = PROJECT_ROOT / rel_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _check_env_file():
    env_path = PROJECT_ROOT / "config.env"
    if not env_path.exists():
        return {"ok": False, "message": "config.env missing"}

    text = env_path.read_text(encoding="utf-8", errors="ignore")
    present_keys = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.strip().startswith("#")}
    important_keys = {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "MT5_LOGIN", "MT5_SERVER", "MT5_PASSWORD"}
    missing = sorted(k for k in important_keys if k not in present_keys)
    return {
        "ok": True,
        "message": "config.env loaded",
        "missing_recommended_keys": missing,
    }


def _check_mt5_package():
    try:
        import MetaTrader5 as mt5  # noqa: F401
        return {"ok": True, "message": "MetaTrader5 package available"}
    except Exception as exc:
        return {
            "ok": False,
            "message": f"MetaTrader5 unavailable: {exc}",
        }


def _module_registry_state():
    state = {}
    for key, module_name in MODULE_REGISTRY.items():
        try:
            importlib.import_module(module_name)
            state[key] = {"status": "ACTIVE", "module": module_name}
        except Exception as exc:
            state[key] = {"status": "ERROR", "module": module_name, "error": str(exc)}
    return state


def _critical_functions_state():
    state = {}
    for module_name, functions in CRITICAL_FUNCTIONS.items():
        try:
            module = importlib.import_module(module_name)
            missing = [fn for fn in functions if not hasattr(module, fn)]
            state[module_name] = {
                "status": "ACTIVE" if not missing else "ERROR",
                "missing": missing,
            }
        except Exception as exc:
            state[module_name] = {"status": "ERROR", "missing": functions, "error": str(exc)}
    return state


def run_startup_check(strict=False):
    created_dirs = []
    for rel_dir in REQUIRED_DIRS:
        created_dirs.append(str(_ensure_dir(rel_dir)))

    env_state = _check_env_file()
    mt5_state = _check_mt5_package()
    module_registry = _module_registry_state()
    critical_functions = _critical_functions_state()
    runtime_validation_report = run_runtime_validation()

    missing_required_files = [p for p in RECOMMENDED_FILES if not _path_exists(p)]
    missing_optional_models = [p for p in OPTIONAL_MODEL_FILES if not _path_exists(p)]
    module_errors = [k for k, v in module_registry.items() if v.get("status") != "ACTIVE"]
    critical_errors = [k for k, v in critical_functions.items() if v.get("status") != "ACTIVE"]

    summary = {
        "project_root": str(PROJECT_ROOT),
        "env": env_state,
        "mt5": mt5_state,
        "created_dirs": created_dirs,
        "missing_required_files": missing_required_files,
        "missing_optional_models": missing_optional_models,
        "module_registry": module_registry,
        "critical_functions": critical_functions,
        "runtime_validation": runtime_validation_report,
        "ready": (
            env_state.get("ok", False)
            and (mt5_state.get("ok", False) or not strict)
            and not module_errors
            and not critical_errors
        ),
    }
    summary["system_status"] = "SYSTEM_READY" if summary["ready"] else "SYSTEM_BLOCKED"
    summary["startup_status"] = summary["system_status"]

    print("[STATUS] STARTUP CHECK")
    print(f"[STATUS] Root: {summary['project_root']}")
    print(f"[STATUS] Env: {'OK' if env_state.get('ok') else 'WARN'} | {env_state.get('message')}")
    print(f"[STATUS] MT5: {'OK' if mt5_state.get('ok') else 'WARN'} | {mt5_state.get('message')}")
    if missing_required_files:
        print(f"[ERROR] Missing files: {', '.join(missing_required_files)}")
    if missing_optional_models:
        print(f"[STATUS] Optional models missing: {', '.join(missing_optional_models)}")
    if module_errors:
        print(f"[ERROR] Module registry errors: {', '.join(module_errors)}")
    if critical_errors:
        print(f"[ERROR] Critical function errors: {', '.join(critical_errors)}")
    print(f"[STATUS] {summary['system_status']}")

    return summary
