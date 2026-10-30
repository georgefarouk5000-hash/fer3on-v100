from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "data" / "models"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    required_path: str
    aliases: tuple[str, ...] = ()
    kind: str = "pickle"


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="XGBoost Model",
        required_path="data/models/xgb_model.pkl",
        aliases=("data/models/xgb_model_sklearn.pkl",),
        kind="pickle",
    ),
    ModelSpec(
        name="XGBoost Scaler",
        required_path="data/models/xgb_scaler.pkl",
        aliases=("data/models/xgb_scaler_sklearn.pkl",),
        kind="pickle",
    ),
    ModelSpec(
        name="Neural Model",
        required_path="data/models/nn_model.pkl",
        aliases=(),
        kind="pickle",
    ),
    ModelSpec(
        name="RL Model",
        required_path="data/models/rl_model.pkl",
        aliases=("data/models/q_table.json",),
        kind="json_or_pickle",
    ),
)

VALID_STATUSES = ("REAL", "PARTIAL", "DISABLED")


def _abs(rel_path: str) -> Path:
    return PROJECT_ROOT / rel_path


def _load_pickle(path: Path) -> tuple[bool, str]:
    try:
        with open(path, "rb") as handle:
            pickle.load(handle)
        return True, "OK"
    except Exception as exc:
        return False, f"INVALID_PICKLE:{exc}"


def _load_json(path: Path) -> tuple[bool, str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            json.load(handle)
        return True, "OK"
    except Exception as exc:
        return False, f"INVALID_JSON:{exc}"


def _validate_path(path: Path, kind: str) -> tuple[bool, str]:
    if not path.exists():
        return False, "MISSING"
    if kind == "pickle":
        return _load_pickle(path)
    if kind == "json":
        return _load_json(path)
    ok, reason = _load_pickle(path)
    if ok:
        return ok, reason
    if path.suffix.lower() == ".json":
        return _load_json(path)
    return ok, reason


class UnifiedMLManager:
    """Centralized ML audit + runtime status + ensemble helpers.

    Notes:
    - REAL requires the exact supported file set requested by the rebuild task.
    - Legacy aliases are allowed for runtime fallback, but they do not upgrade status to REAL.
    - Status vocabulary is strictly limited to: REAL / PARTIAL / DISABLED.
    """

    def __init__(self) -> None:
        self.specs = MODEL_SPECS

    def _resolve_candidate(self, spec: ModelSpec) -> Dict[str, Any]:
        required_abs = _abs(spec.required_path)
        required_ok, required_reason = _validate_path(required_abs, spec.kind)

        alias_hits: List[Dict[str, str]] = []
        for alias in spec.aliases:
            alias_abs = _abs(alias)
            alias_ok, alias_reason = _validate_path(alias_abs, spec.kind)
            if alias_abs.exists():
                alias_hits.append(
                    {
                        "path": alias,
                        "status": "VALID" if alias_ok else "INVALID",
                        "reason": alias_reason,
                    }
                )

        runtime_path = spec.required_path if required_ok else None
        runtime_source = "required"
        if runtime_path is None:
            for hit in alias_hits:
                if hit["status"] == "VALID":
                    runtime_path = hit["path"]
                    runtime_source = "legacy_alias"
                    break

        return {
            "name": spec.name,
            "required_path": spec.required_path,
            "required_exists": required_abs.exists(),
            "required_valid": required_ok,
            "required_reason": required_reason,
            "aliases": alias_hits,
            "runtime_path": runtime_path,
            "runtime_source": runtime_source if runtime_path else None,
            "usable": bool(runtime_path),
            "exact_ready": bool(required_ok),
        }

    def audit_models(self) -> Dict[str, Any]:
        details = [self._resolve_candidate(spec) for spec in self.specs]
        exact_ready = [d for d in details if d["exact_ready"]]
        usable = [d for d in details if d["usable"]]
        missing_required = [d["required_path"] for d in details if not d["exact_ready"]]
        legacy_runtime = [d["runtime_path"] for d in details if d["runtime_source"] == "legacy_alias"]

        if len(exact_ready) == len(details):
            status = "REAL"
        elif usable:
            status = "PARTIAL"
        else:
            status = "DISABLED"

        return {
            "status": status,
            "details": details,
            "usable_count": len(usable),
            "required_count": len(details),
            "missing_required_files": missing_required,
            "legacy_runtime_files": legacy_runtime,
            "runtime_files": [d["runtime_path"] for d in details if d["runtime_path"]],
        }

    def build_status_report(
        self,
        *,
        feature_count: int = 0,
        training_trades: int = 0,
        model_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        audit = self.audit_models()
        details_by_name = {item["name"]: item for item in audit["details"]}
        available_models = sorted(
            name for name, item in details_by_name.items() if item.get("usable")
        )
        missing_models = sorted(
            name for name, item in details_by_name.items() if not item.get("usable")
        )
        exact_missing = list(audit.get("missing_required_files", []))
        runtime_source = "MODEL" if audit["status"] == "REAL" else ("FALLBACK" if available_models else "DISABLED")
        return {
            "status": audit["status"],
            "confidence_source": runtime_source,
            "available_models": available_models,
            "missing_models": missing_models,
            "missing_files": exact_missing,
            "feature_count": int(feature_count or 0),
            "training_trades": int(training_trades or 0),
            "model_details": model_details or {},
            "details": audit["details"],
            "runtime_files": audit["runtime_files"],
            "legacy_runtime_files": audit["legacy_runtime_files"],
        }

    def fallback_result(self, reason: str, *, rl_result: Optional[Dict[str, Any]] = None, feature_count: int = 0) -> Dict[str, Any]:
        rl_result = rl_result or {}
        status_report = self.build_status_report(feature_count=feature_count, training_trades=0)
        return {
            "approved": True,
            "ml_score": 50.0,
            "ensemble_prob": 0.5,
            "gbm_prob": 0.5,
            "nn_prob": 0.5,
            "rl_action": rl_result.get("action", "PASS"),
            "lot_mult": rl_result.get("lot_mult", 1.0) if rl_result.get("trusted") else 1.0,
            "confidence_boost": 0,
            "reason": reason,
            "models_trained": False,
            "gbm_engine": "NONE",
            "xgb_prediction": "NEUTRAL",
            "xgb_probability": 50.0,
            "xgb_confidence": 0.0,
            "feature_importance": {},
            "feature_snapshot": {},
            "nn_prediction": "NEUTRAL",
            "nn_probability": 50.0,
            "nn_confidence": 0.0,
            "nn_top_features": {},
            "rl_confidence": rl_result.get("confidence", 0.0),
            "rl_policy_mode": rl_result.get("policy_mode", "WARMUP"),
            "rl_state_visits": rl_result.get("state_visits", 0),
            "rl_trusted": rl_result.get("trusted", False),
            "rl_q_values": rl_result.get("q_values", []),
            "model_confidence": 0.0,
            "advisory_only": True,
            "ml_failure": True,
            "ml_status": status_report.get("status", "DISABLED"),
            "feature_count": feature_count,
            "missing_files": status_report.get("missing_files", []),
        }

    @staticmethod
    def calculate_ensemble(
        *,
        gbm_result: Optional[Dict[str, Any]] = None,
        nn_result: Optional[Dict[str, Any]] = None,
        rl_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        gbm_result = gbm_result or {}
        nn_result = nn_result or {}
        rl_result = rl_result or {}

        gbm_w = 0.52 if gbm_result.get("trained") else 0.0
        nn_w = 0.33 if nn_result.get("trained") else 0.0
        rl_w = 0.15 if rl_result.get("trusted") else 0.0
        total_w = gbm_w + nn_w + rl_w

        rl_action_prob = {
            "ENTER_FULL": 0.68,
            "ENTER_HALF": 0.58,
            "ENTER_QUARTER": 0.53,
            "SKIP": 0.35,
            "PASS": 0.50,
        }.get(rl_result.get("action"), 0.50)

        if total_w > 0:
            ensemble_prob = (
                gbm_result.get("win_prob", 0.5) * gbm_w
                + nn_result.get("win_prob", 0.5) * nn_w
                + rl_action_prob * rl_w
            ) / total_w
        else:
            ensemble_prob = 0.5

        weighted_confidence = 0.0
        if total_w > 0:
            weighted_confidence = (
                gbm_result.get("model_confidence", 0.0) * gbm_w
                + nn_result.get("model_confidence", 0.0) * nn_w
                + rl_result.get("confidence", 0.0) * rl_w
            ) / total_w

        return {
            "gbm_weight": gbm_w,
            "nn_weight": nn_w,
            "rl_weight": rl_w,
            "total_weight": total_w,
            "ensemble_prob": round(float(ensemble_prob), 3),
            "model_confidence": round(float(weighted_confidence), 1),
        }

    @staticmethod
    def confidence_boost(ensemble_prob: float, total_weight: float) -> int:
        if total_weight <= 0:
            return 0
        if ensemble_prob >= 0.80:
            return 20
        if ensemble_prob >= 0.65:
            return 10
        if ensemble_prob >= 0.50:
            return 0
        if ensemble_prob >= 0.35:
            return -8
        return -12

    def generate_markdown_audit(self) -> str:
        audit = self.audit_models()
        lines = [
            "# ML Status Report",
            "",
            f"- Status: **{audit['status']}**",
            f"- Usable runtime artifacts: **{audit['usable_count']} / {audit['required_count']}**",
            "",
            "## Exact supported model files",
            "",
        ]
        for item in audit["details"]:
            exact_state = "VALID" if item["exact_ready"] else ("MISSING" if not item["required_exists"] else "INVALID")
            lines.append(f"- **{item['name']}** → `{item['required_path']}` → **{exact_state}**")
            if item["aliases"]:
                for alias in item["aliases"]:
                    lines.append(
                        f"  - legacy alias: `{alias['path']}` → **{alias['status']}**"
                        + (f" ({alias['reason']})" if alias['reason'] != 'OK' else "")
                    )
            if item["runtime_path"]:
                lines.append(f"  - runtime source: `{item['runtime_path']}` ({item['runtime_source']})")
            else:
                lines.append("  - runtime source: none")
            if item["required_reason"] not in {"OK", "MISSING"}:
                lines.append(f"  - exact validation: `{item['required_reason']}`")
        lines.extend([
            "",
            "## Missing exact files",
            "",
        ])
        if audit["missing_required_files"]:
            lines.extend(f"- `{path}`" for path in audit["missing_required_files"])
        else:
            lines.append("- None")
        return "\n".join(lines) + "\n"


_manager: Optional[UnifiedMLManager] = None


def get_ml_manager() -> UnifiedMLManager:
    global _manager
    if _manager is None:
        _manager = UnifiedMLManager()
    return _manager
