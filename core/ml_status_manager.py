import json
from pathlib import Path
from typing import Dict, List, Optional

from core.settings import ML_FEATURE_COUNT
from ml.ml_manager import get_ml_manager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "data" / "models" / "registry.json"
ML_STATUSES = ("DISABLED", "PARTIAL", "REAL")


def _ensure_registry_path() -> Path:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text("{}", encoding="utf-8")
    return REGISTRY_PATH


def _load_registry() -> Dict[str, Dict[str, object]]:
    try:
        data = json.loads(_ensure_registry_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(registry: Dict[str, Dict[str, object]]) -> None:
    _ensure_registry_path().write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def update_ml_registry(
    model_name: str,
    *,
    version: str = "unknown",
    feature_count: int = 0,
    training_trades: int = 0,
    status: str = "MISSING",
    file_path: str = "",
) -> Dict[str, object]:
    registry = _load_registry()
    entry = {
        "model_name": model_name,
        "version": version,
        "created_date": str(__import__("datetime").datetime.utcnow().isoformat()) + "Z",
        "feature_count": int(feature_count or 0),
        "training_trades": int(training_trades or 0),
        "status": status,
        "file_path": file_path,
    }
    registry[model_name] = entry
    _save_registry(registry)
    return entry


def build_ml_status_report(
    *,
    model_files: Optional[List[str]] = None,
    feature_count: int = ML_FEATURE_COUNT,
    training_trades: int = 0,
    model_details: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    # عند تمرير model_files=[] صراحةً → لا نماذج متاحة → DISABLED فوراً
    if model_files is not None and len(model_files) == 0:
        return {
            "status": "DISABLED",
            "confidence_source": "FALLBACK",
            "available_models": [],
            "missing_models": [],
            "missing_files": [],
            "feature_count": int(feature_count or 0),
            "training_trades": int(training_trades or 0),
            "model_details": model_details or {},
            "details": [],
            "runtime_files": [],
            "legacy_runtime_files": [],
            "registry_path": str(REGISTRY_PATH),
            "registry": _load_registry(),
        }
    manager = get_ml_manager()
    report = manager.build_status_report(
        feature_count=feature_count,
        training_trades=training_trades,
        model_details=model_details,
    )

    for item in report.get("details", []):
        update_ml_registry(
            item["name"],
            feature_count=feature_count,
            training_trades=training_trades,
            status="LOADED" if item.get("usable") else "MISSING",
            file_path=item.get("runtime_path") or item.get("required_path", ""),
        )

    report["registry_path"] = str(REGISTRY_PATH)
    report["registry"] = _load_registry()
    return report


def format_ml_status_report(report: Dict[str, object]) -> str:
    missing_files = report.get("missing_files", []) or []
    missing_text = ", ".join(str(path) for path in missing_files) if missing_files else "None"
    return (
        f"ML STATUS: {report.get('status', 'DISABLED')}\n"
        f"Available Models: {', '.join(report.get('available_models', [])) or 'None'}\n"
        f"Missing Models: {', '.join(report.get('missing_models', [])) or 'None'}\n"
        f"Missing Files: {missing_text}\n"
        f"Feature Count: {report.get('feature_count', 0)}\n"
        f"Training Trades: {report.get('training_trades', 0)}\n"
        f"Confidence Source: {report.get('confidence_source', 'DISABLED')}"
    )
