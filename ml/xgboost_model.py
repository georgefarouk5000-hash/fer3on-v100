# =========================================
# FER3ON AI V2.2 — XGBOOST / GBM PREDICTOR
# 22-feature advisory model with safe fallback
# XGBoost إذا متاح، وإلا GradientBoosting
# =========================================

import os
import json
import pickle
import warnings
import numpy as np

from core.settings import ML_FEATURE_COUNT
from brain.trade_dna import ML_FEATURE_SCHEMA_VERSION
warnings.filterwarnings("ignore")

MODEL_FILE  = "data/models/xgb_model.pkl"
SCALER_FILE = "data/models/xgb_scaler.pkl"
LEGACY_MODEL_FILE = "data/models/xgb_model_sklearn.pkl"
LEGACY_SCALER_FILE = "data/models/xgb_scaler_sklearn.pkl"
MIN_SAMPLES = 30

# =========================================
# LAZY DEPENDENCY CHECK
# لا import في المستوى العلوي → لا crash
# =========================================

def _check_sklearn():
    """يتحقق من توفر scikit-learn بدون crash"""
    try:
        import sklearn  # noqa
        return True
    except ImportError:
        return False

def _check_xgboost():
    """يتحقق من توفر xgboost"""
    try:
        import xgboost  # noqa
        return True
    except ImportError:
        return False

HAS_SKLEARN = _check_sklearn()
HAS_XGB     = _check_xgboost() and HAS_SKLEARN

try:
    import joblib  # noqa
except ImportError:  # pragma: no cover - optional dependency
    joblib = None

if not HAS_SKLEARN:
    print(
        "⚠️  scikit-learn غير مثبّت.\n"
        "   شغّل: pip install scikit-learn numpy\n"
        "   أو:   install.bat\n"
        "   سيعمل البوت بدون ML حتى يتم التثبيت."
    )

if HAS_SKLEARN and not HAS_XGB:
    print("ℹ️  xgboost غير متاح — سيُستخدم GradientBoosting تلقائياً ✅")

if HAS_XGB:
    print("✅ XGBoost متاح")


# =========================================
# GRADIENT BOOSTING PREDICTOR
# =========================================

def _load_artifact(path, label):
    if not os.path.exists(path):
        return None

    try:
        if joblib is not None:
            return joblib.load(path)
        with open(path, "rb") as handle:
            return pickle.load(handle)
    except Exception as exc:
        print(f"⚠️  {label} artifact is incompatible or corrupted and will be reset: {exc}")
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def _load_with_legacy_alias(primary_path, legacy_path, label):
    artifact = _load_artifact(primary_path, label)
    if artifact is not None:
        return artifact, primary_path
    artifact = _load_artifact(legacy_path, f"{label} (legacy)")
    if artifact is not None:
        return artifact, legacy_path
    return None, None


def _build_primary_model(prefer_xgboost=True):
    if prefer_xgboost:
        try:
            from xgboost import XGBClassifier
            return XGBClassifier(
                n_estimators=200,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                gamma=0.1,
                reg_alpha=0.1,
                reg_lambda=1.0,
                eval_metric="logloss",
                random_state=42,
                verbosity=0,
            ), "XGBoost"
        except Exception as exc:
            print(f"⚠️  XGBoost unavailable; using GradientBoosting instead: {exc}")

    from sklearn.ensemble import GradientBoostingClassifier
    return GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=3,
        random_state=42,
    ), "GradientBoosting"


class GBMPredictor:
    """
    نموذج Gradient Boosting للتنبؤ بنتائج الصفقات.
    يستخدم XGBoost إذا متاح، وإلا GradientBoosting من sklearn.
    إذا لم يتوفر sklearn: يعود دائماً 0.5 (neutral).
    """

    def __init__(self):
        self.model     = None
        self.scaler    = None
        self.trained   = False
        self.cv_score  = 0.0
        self.n_samples = 0
        self.engine    = "NONE"
        self.feature_count = 0
        self._load()

    # ─────────────────────────────────────
    # LOAD
    # ─────────────────────────────────────
    def _load(self):
        self.model = None
        self.scaler = None
        self.trained = False
        self.cv_score = 0.0
        self.n_samples = 0
        self.engine = "NONE"
        self.feature_count = 0

        if not HAS_SKLEARN:
            return
        try:
            model_blob, model_path = _load_with_legacy_alias(MODEL_FILE, LEGACY_MODEL_FILE, "GBM model")
            scaler_blob, scaler_path = _load_with_legacy_alias(SCALER_FILE, LEGACY_SCALER_FILE, "GBM scaler")

            if model_blob is not None and scaler_blob is not None:
                if not (
                    isinstance(model_blob, dict)
                    and isinstance(scaler_blob, dict)
                    and model_blob.get("feature_schema_version") == ML_FEATURE_SCHEMA_VERSION
                    and scaler_blob.get("feature_schema_version") == ML_FEATURE_SCHEMA_VERSION
                ):
                    print(
                        "[ML FAILURE] GBM artifact feature schema is stale or missing; "
                        "advisory fallback until retrained"
                    )
                    return

                self.model = model_blob.get("model") if isinstance(model_blob, dict) else model_blob
                self.scaler = scaler_blob.get("scaler") if isinstance(scaler_blob, dict) else scaler_blob
                self.feature_count = int(
                    (model_blob.get("feature_count") if isinstance(model_blob, dict) else 0)
                    or (scaler_blob.get("feature_count") if isinstance(scaler_blob, dict) else 0)
                    or getattr(self.model, "n_features_in_", 0)
                    or getattr(self.scaler, "n_features_in_", 0)
                    or 0
                )
                self.trained = self.model is not None and self.scaler is not None
                if self.model is not None and type(self.model).__module__.startswith("xgboost"):
                    self.engine = "XGBoost"
                else:
                    self.engine = "GradientBoosting"
                if self.trained and self.feature_count not in (0, ML_FEATURE_COUNT):
                    print(f"[ML FAILURE] GBM feature mismatch on load: expected {ML_FEATURE_COUNT}, got {self.feature_count} — advisory fallback")
                    self.model = None
                    self.scaler = None
                    self.trained = False
                    self.feature_count = 0
                    self.engine = "NONE"
                elif self.trained:
                    print(
                        f"✅ GBM model loaded | Engine:{self.engine} | features={self.feature_count or ML_FEATURE_COUNT}"
                        f" | model={model_path or MODEL_FILE} | scaler={scaler_path or SCALER_FILE}"
                    )
        except Exception as e:
            print(f"⚠️  GBM load error: {e}")

    # ─────────────────────────────────────
    # TRAIN
    # ─────────────────────────────────────
    def train(self, X, y):
        if not HAS_SKLEARN:
            print("❌ GBM train: scikit-learn غير متاح")
            return False

        if len(X) < MIN_SAMPLES:
            print(f"⚠️  GBM: Need {MIN_SAMPLES} samples, got {len(X)}")
            return False

        from sklearn.preprocessing   import StandardScaler
        from sklearn.model_selection import cross_val_score

        if self.scaler is None:
            self.scaler = StandardScaler()

        X_scaled = self.scaler.fit_transform(X)

        self.model, self.engine = _build_primary_model(prefer_xgboost=HAS_XGB)

        # Cross-validation
        try:
            n_cv = min(5, max(2, len(X) // 10))
            cv_scores = cross_val_score(
                self.model, X_scaled, y,
                cv=n_cv, scoring="roc_auc"
            )
            self.cv_score = round(float(cv_scores.mean()), 3)
        except Exception:
            self.cv_score = 0.0

        self.model.fit(X_scaled, y)
        self.trained   = True
        self.n_samples = len(X)
        self.feature_count = int(X.shape[1]) if len(X.shape) > 1 else 0

        # حفظ
        os.makedirs("data/models", exist_ok=True)
        try:
            os.makedirs("data/models", exist_ok=True)
            if joblib is not None:
                joblib.dump({
                    "model": self.model,
                    "feature_count": self.feature_count,
                    "feature_schema_version": ML_FEATURE_SCHEMA_VERSION,
                }, MODEL_FILE)
                joblib.dump({
                    "scaler": self.scaler,
                    "feature_count": self.feature_count,
                    "feature_schema_version": ML_FEATURE_SCHEMA_VERSION,
                }, SCALER_FILE)
            else:
                with open(MODEL_FILE, "wb") as handle:
                    pickle.dump({
                        "model": self.model,
                        "feature_count": self.feature_count,
                        "feature_schema_version": ML_FEATURE_SCHEMA_VERSION,
                    }, handle)
                with open(SCALER_FILE, "wb") as handle:
                    pickle.dump({
                        "scaler": self.scaler,
                        "feature_count": self.feature_count,
                        "feature_schema_version": ML_FEATURE_SCHEMA_VERSION,
                    }, handle)
        except Exception as e:
            print(f"⚠️  GBM save error: {e}")

        print(
            f"✅ GBM trained | Engine:{self.engine}"
            f" | n={len(X)} | features={self.feature_count} | CV-AUC={self.cv_score}"
        )
        return True

    # ─────────────────────────────────────
    # PREDICT
    # ─────────────────────────────────────
    def predict_proba(self, features):
        """يُعيد احتمال الربح (0.0 - 1.0)"""
        if not self.trained or self.model is None or self.scaler is None:
            return 0.5
        try:
            X = np.array(features, dtype=np.float32).reshape(1, -1)
            if self.feature_count and X.shape[1] != self.feature_count:
                print(f"[ML FAILURE] GBM feature mismatch: expected {self.feature_count}, got {X.shape[1]} — advisory fallback")
                return 0.5
            X_scaled = self.scaler.transform(X)
            proba = self.model.predict_proba(X_scaled)[0]
            return round(float(proba[1]), 3)
        except Exception as e:
            print(f"⚠️  GBM predict error: {e}")
            return 0.5

    # ─────────────────────────────────────
    def get_feature_importance(self, feature_names):
        if not self.trained or not hasattr(self.model, "feature_importances_"):
            return {}
        imp = self.model.feature_importances_
        return {
            n: round(float(v), 4)
            for n, v in sorted(zip(feature_names, imp), key=lambda x: -x[1])
        }

    def get_stats(self):
        return {
            "trained":   self.trained,
            "n_samples": self.n_samples,
            "cv_auc":    self.cv_score,
            "engine":    self.engine,
            "feature_count": self.feature_count,
        }


# =========================================
# SINGLETON
# =========================================

_predictor = None

def get_gbm_predictor() -> GBMPredictor:
    global _predictor
    if _predictor is None:
        _predictor = GBMPredictor()
    return _predictor


# =========================================
# TRAIN FROM DNA
# =========================================

def train_from_dna():
    """يدرّب النموذج من بيانات Trade DNA"""
    if not HAS_SKLEARN:
        return {
            "trained": False,
            "reason":  "scikit-learn not installed — run: pip install scikit-learn"
        }

    try:
        from brain.trade_dna import load_trade_dna, get_ml_features, FEATURE_NAMES
    except ImportError as e:
        return {"trained": False, "reason": f"Import error: {e}"}

    data = load_trade_dna()
    if len(data) < MIN_SAMPLES:
        return {
            "trained": False,
            "reason":  f"Need {MIN_SAMPLES} trades, have {len(data)}"
        }

    X, y = [], []
    for rec in data:
        result = rec.get("result", "")
        if result not in ("WIN", "LOSS"):
            continue
        try:
            feats = get_ml_features(rec)
            X.append(feats)
            y.append(1 if result == "WIN" else 0)
        except Exception:
            continue

    if len(X) < MIN_SAMPLES:
        return {"trained": False, "reason": f"Valid samples: {len(X)}"}

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=int)

    pred = get_gbm_predictor()
    ok   = pred.train(X, y)

    importance = pred.get_feature_importance(FEATURE_NAMES)

    return {
        "trained":      ok,
        "n_samples":    len(X),
        "win_rate":     round(float(y.mean()) * 100, 1),
        "cv_auc":       pred.cv_score,
        "engine":       pred.engine,
        "feature_count": int(X.shape[1]) if len(X.shape) > 1 else 0,
        "top_features": dict(list(importance.items())[:5]),
    }


# =========================================
# LIVE DIAGNOSTICS
# =========================================

def get_live_model_diagnostics(features_array, feature_names=None, top_n=5):
    pred = get_gbm_predictor()
    if not pred.trained:
        return {
            "engine": pred.engine or "NONE",
            "top_features": {},
            "feature_confidence": 0.0,
        }

    feature_names = feature_names or []
    try:
        importance = pred.get_feature_importance(feature_names)
        top_features = dict(list(importance.items())[:top_n]) if importance else {}
    except Exception:
        top_features = {}

    try:
        win_prob = pred.predict_proba(features_array)
        feature_confidence = round(abs(win_prob - 0.5) * 200, 1)
    except Exception:
        feature_confidence = 0.0

    return {
        "engine": pred.engine,
        "top_features": top_features,
        "feature_confidence": feature_confidence,
    }


# =========================================
# PREDICT TRADE WIN PROBABILITY
# =========================================

def predict_trade_win_prob(features_array):
    """
    يُعيد:
      win_prob : 0.0-1.0
      grade    : EXCELLENT | GOOD | NEUTRAL | WEAK | REJECT
      boost    : confidence boost للـ Confidence Engine
      trained  : bool
    """
    pred     = get_gbm_predictor()
    win_prob = pred.predict_proba(features_array)
    model_conf = round(abs(win_prob - 0.5) * 200, 1)

    if not pred.trained:
        return {
            "win_prob": 0.5,
            "grade":    "NEUTRAL",
            "boost":    0,
            "trained":  False,
            "engine":   pred.engine or "NONE",
            "model_confidence": 0.0,
        }

    if   win_prob >= 0.80: grade, boost = "EXCELLENT",  15
    elif win_prob >= 0.65: grade, boost = "GOOD",         8
    elif win_prob >= 0.50: grade, boost = "NEUTRAL",      0
    elif win_prob >= 0.35: grade, boost = "WEAK",        -5
    else:                  grade, boost = "REJECT",     -15

    print(
        f"🤖 GBM | WIN_PROB={win_prob:.1%}"
        f" | Grade:{grade}"
        f" | Boost:{boost:+d}"
        f" | Conf:{model_conf:.1f}"
        f" | Engine:{pred.engine}"
    )

    return {
        "win_prob": win_prob,
        "grade":    grade,
        "boost":    boost,
        "trained":  True,
        "engine":   pred.engine,
        "model_confidence": model_conf,
    }
