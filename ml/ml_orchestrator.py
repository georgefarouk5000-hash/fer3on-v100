# =========================================
# FER3ON V2.2 — ML ORCHESTRATOR
# Advisory-only ML layer with neutral fallback
# =========================================

from brain.trade_dna import FEATURE_NAMES
from core.settings import ML_FEATURE_COUNT
from core.ml_status_manager import build_ml_status_report, format_ml_status_report
from ml.ml_manager import get_ml_manager
from ml.xgboost_model import (
    predict_trade_win_prob,
    get_live_model_diagnostics,
)
from ml.neural_network import nn_predict_win_prob
from ml.reinforcement import encode_state, rl_get_action, rl_update, ACTION_IDX


# =========================================
# HELPERS
# =========================================


def _neutral_advisory_result(reason, rl_result=None, feature_count=0):
    return get_ml_manager().fallback_result(
        reason,
        rl_result=rl_result or {},
        feature_count=feature_count,
    )


# =========================================
# ML UNIFIED DECISION
# =========================================


def ml_evaluate_trade(
    features_array,
    state_key,
    signal,
    quality_score,
    exec_grade,
    market_regime="UNKNOWN",
    session="UNKNOWN",
    mtf_strength=0,
    choch_active=False,
    liq_score=0,
):
    rl_result = rl_get_action(state_key)

    feature_count = len(list(features_array)) if features_array is not None else 0
    ml_status_report = build_ml_status_report(
        model_files=[
            "data/models/xgb_model.pkl",
            "data/models/xgb_scaler.pkl",
            "data/models/nn_model.pkl",
            "data/models/rl_model.pkl",
        ],
        feature_count=feature_count,
        training_trades=0,
    )
    if feature_count != ML_FEATURE_COUNT:
        print(f"[ML STATUS] FALLBACK | feature_count={feature_count} expected={ML_FEATURE_COUNT}")
        print(format_ml_status_report(ml_status_report))
        return _neutral_advisory_result(
            f"ML_FALLBACK_FEATURE_MISMATCH:{feature_count}!={ML_FEATURE_COUNT}",
            rl_result=rl_result,
            feature_count=feature_count,
        )

    try:
        gbm_result = predict_trade_win_prob(features_array)
        nn_result = nn_predict_win_prob(features_array, FEATURE_NAMES)
        xgb_diag = get_live_model_diagnostics(features_array, FEATURE_NAMES)
    except Exception as exc:  # pragma: no cover - defensive fallback
        print(f"[ML FAILURE] advisory fallback | {exc}")
        return _neutral_advisory_result(
            f"ML_FALLBACK_EXCEPTION:{exc}",
            rl_result=rl_result,
            feature_count=feature_count,
        )

    ensemble_meta = get_ml_manager().calculate_ensemble(
        gbm_result=gbm_result,
        nn_result=nn_result,
        rl_result=rl_result,
    )
    ensemble_prob = ensemble_meta["ensemble_prob"]
    total_w = ensemble_meta["total_weight"]
    ml_score = round(ensemble_prob * 100, 1)
    model_confidence = ensemble_meta["model_confidence"]
    boost = get_ml_manager().confidence_boost(ensemble_prob, total_w)

    if total_w == 0 and not rl_result.get("trusted"):
        reason = "ML_FALLBACK_NEUTRAL: no trained models yet"
    elif rl_result.get("action") == "SKIP" and rl_result.get("trusted") and ensemble_prob < 0.52:
        reason = (
            f"ML_ADVISORY_LOW_PROB: GBM={gbm_result.get('win_prob', 0.5):.0%}"
            f" NN={nn_result.get('win_prob', 0.5):.0%} RL=SKIP"
        )
    elif total_w > 0 and ensemble_prob < 0.32:
        reason = f"ML_ADVISORY_LOW_PROB: ensemble={ensemble_prob:.0%}"
    else:
        reason = (
            f"ML_OK: ensemble={ensemble_prob:.0%}"
            f" RL={rl_result.get('action')}"
            f" mode={rl_result.get('policy_mode')}"
        )

    top_feats = xgb_diag.get("top_features", {})
    nn_top_feats = nn_result.get("top_features", {})
    feat_txt = ", ".join(f"{k}={v:.3f}" for k, v in list(top_feats.items())[:3]) if top_feats else "n/a"

    ml_status = ml_status_report.get("status", "DISABLED")
    if ml_status not in {"DISABLED", "PARTIAL", "REAL"}:
        ml_status = "DISABLED"
    ml_status_report = build_ml_status_report(
        model_files=[
            "data/models/xgb_model.pkl",
            "data/models/xgb_scaler.pkl",
            "data/models/nn_model.pkl",
            "data/models/rl_model.pkl",
        ],
        feature_count=feature_count,
        training_trades=0,
    )
    print(
        f"[STATUS] ML ENSEMBLE"
        f" | ML_STATUS:{ml_status}"
        f" | XGB:{gbm_result.get('win_prob', 0.5):.0%}"
        f" | NN:{nn_result.get('win_prob', 0.5):.0%}"
        f" | RL:{rl_result.get('action')}"
        f" | Ensemble:{ensemble_prob:.0%}"
        f" | ModelConf:{model_confidence:.1f}"
        f" | Boost:{boost:+d}"
        f" | Feats:{feat_txt}"
        f" | feature_count={feature_count}"
    )
    print(format_ml_status_report(ml_status_report))

    effective_lot_mult = rl_result.get("lot_mult", 1.0) if rl_result.get("trusted") else 1.0

    return {
        "approved": True,
        "ml_score": ml_score,
        "ensemble_prob": round(ensemble_prob, 3),
        "gbm_prob": gbm_result.get("win_prob", 0.5),
        "nn_prob": nn_result.get("win_prob", 0.5),
        "rl_action": rl_result.get("action", "ENTER_QUARTER"),
        "lot_mult": effective_lot_mult,
        "confidence_boost": boost,
        "reason": reason,
        "models_trained": total_w > 0,
        "gbm_engine": gbm_result.get("engine", "NONE"),
        "xgb_prediction": gbm_result.get("grade", "NEUTRAL"),
        "xgb_probability": round(float(gbm_result.get("win_prob", 0.5) or 0.5) * 100, 1),
        "xgb_confidence": gbm_result.get("model_confidence", xgb_diag.get("feature_confidence", 0.0)),
        "feature_importance": top_feats,
        "feature_snapshot": nn_result.get("feature_snapshot", {}),
        "nn_prediction": nn_result.get("prediction", nn_result.get("grade", "NEUTRAL")),
        "nn_probability": round(float(nn_result.get("win_prob", 0.5) or 0.5) * 100, 1),
        "nn_confidence": nn_result.get("model_confidence", 0.0),
        "nn_top_features": nn_top_feats,
        "rl_confidence": rl_result.get("confidence", 0.0),
        "rl_policy_mode": rl_result.get("policy_mode", "WARMUP"),
        "rl_state_visits": rl_result.get("state_visits", 0),
        "rl_trusted": rl_result.get("trusted", False),
        "rl_q_values": rl_result.get("q_values", []),
        "model_confidence": model_confidence,
        "advisory_only": True,
        "ml_failure": total_w == 0,
        "ml_status": ml_status,
        "feature_count": feature_count,
        "missing_files": ml_status_report.get("missing_files", []),
    }


# =========================================
# POST-TRADE RL UPDATE
# =========================================


def ml_post_trade_update(
    old_state_key,
    action_name,
    result,
    profit,
    rr_ratio,
    quality_score,
    exec_grade,
    new_state_key,
):
    if action_name not in ACTION_IDX:
        return 0.0
    reward = rl_update(
        state_key=old_state_key,
        action_idx=ACTION_IDX[action_name],
        result=result,
        profit=profit,
        rr_ratio=rr_ratio,
        quality_score=quality_score,
        exec_grade=exec_grade,
        next_state_key=new_state_key,
    )
    return reward


# =========================================
# RETRAIN ALL MODELS
# =========================================


def retrain_all_models():
    from ml.xgboost_model import train_from_dna
    from ml.neural_network import train_nn_from_dna

    print("\n[STATUS] ML RETRAIN START...")
    gbm_r = train_from_dna()
    nn_r = train_nn_from_dna()
    print(
        f"[STATUS] ML RETRAIN DONE"
        f" | GBM:{gbm_r.get('trained')} features={gbm_r.get('feature_count', 'n/a')} AUC:{gbm_r.get('cv_auc', 0)}"
        f" | NN:{nn_r.get('trained')} features={nn_r.get('feature_count', 'n/a')} AUC:{nn_r.get('cv_auc', 0)}"
    )
    return {"gbm": gbm_r, "nn": nn_r}
