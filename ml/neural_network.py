# =========================================
# FER3ON AI V2.2 — NEURAL NETWORK (MLP)
# 22-feature advisory model with safe fallback
# =========================================

import os
import numpy as np
import warnings

from core.settings import ML_FEATURE_COUNT
from brain.trade_dna import ML_FEATURE_SCHEMA_VERSION
warnings.filterwarnings("ignore")

NN_MODEL_FILE = "data/models/nn_model.pkl"
MIN_SAMPLES = 40


# =========================================
# LAZY CHECK
# =========================================


def _check_sklearn():
    try:
        import sklearn  # noqa
        return True
    except ImportError:
        return False


HAS_SKLEARN = _check_sklearn()

if not HAS_SKLEARN:
    print("⚠️  Neural Network: scikit-learn غير متاح — NN disabled")


# =========================================
# NEURAL PREDICTOR
# =========================================


class NeuralPredictor:
    """
    MLP: Input(22) → Dense(64,32,16) → Output(2)
    FER3ON AI V2.2:
      - 22-feature advisory model
      - Predict / Probability / Confidence
      - Feature contribution visibility
      - Safe neutral fallback on feature mismatch
    """

    def __init__(self):
        self.model = None
        self.scaler = None
        self.trained = False
        self.cv_score = 0.0
        self.n_samples = 0
        self.feature_count = 0
        self._load()

    def _load(self):
        if not HAS_SKLEARN:
            return
        try:
            if os.path.exists(NN_MODEL_FILE):
                import pickle
                with open(NN_MODEL_FILE, "rb") as f:
                    saved = pickle.load(f)
                if not isinstance(saved, dict) or saved.get("feature_schema_version") != ML_FEATURE_SCHEMA_VERSION:
                    print(
                        "[ML FAILURE] NN artifact feature schema is stale or missing; "
                        "advisory fallback until retrained"
                    )
                    return
                self.model = saved.get("model")
                self.scaler = saved.get("scaler")
                self.cv_score = float(saved.get("cv_score", 0.0) or 0.0)
                self.n_samples = int(saved.get("n_samples", 0) or 0)
                self.feature_count = int(saved.get("feature_count") or getattr(self.model, "n_features_in_", 0) or getattr(self.scaler, "n_features_in_", 0) or 0)
                self.trained = self.model is not None and self.scaler is not None
                if self.trained and self.feature_count not in (0, ML_FEATURE_COUNT):
                    print(f"[ML FAILURE] NN feature mismatch on load: expected {ML_FEATURE_COUNT}, got {self.feature_count} — advisory fallback")
                    self.model = None
                    self.scaler = None
                    self.trained = False
                    self.feature_count = 0
                elif self.trained:
                    print(f"✅ Neural Network loaded from disk | features={self.feature_count or ML_FEATURE_COUNT}")
        except Exception as e:
            print(f"⚠️  NN load error: {e}")

    def train(self, X, y):
        if not HAS_SKLEARN:
            print("❌ NN train: scikit-learn غير متاح")
            return False

        if len(X) < MIN_SAMPLES:
            print(f"⚠️  NN: Need {MIN_SAMPLES} samples, got {len(X)}")
            return False

        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import cross_val_score

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = MLPClassifier(
            hidden_layer_sizes=(64, 32, 16),
            activation="relu",
            solver="adam",
            alpha=0.001,
            learning_rate_init=0.001,
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=42,
            verbose=False,
        )

        try:
            n_cv = min(5, max(2, len(X) // 8))
            cv_scores = cross_val_score(self.model, X_scaled, y, cv=n_cv, scoring="roc_auc")
            self.cv_score = round(float(cv_scores.mean()), 3)
        except Exception:
            self.cv_score = 0.0

        self.model.fit(X_scaled, y)
        self.trained = True
        self.n_samples = len(X)
        self.feature_count = int(X.shape[1]) if len(X.shape) > 1 else 0

        os.makedirs("data/models", exist_ok=True)
        try:
            import pickle
            with open(NN_MODEL_FILE, "wb") as f:
                pickle.dump(
                    {
                        "model": self.model,
                        "scaler": self.scaler,
                        "cv_score": self.cv_score,
                        "n_samples": self.n_samples,
                        "feature_count": self.feature_count,
                        "feature_schema_version": ML_FEATURE_SCHEMA_VERSION,
                    },
                    f,
                )
        except Exception as e:
            print(f"⚠️  NN save error: {e}")

        print(
            f"✅ Neural Network trained"
            f" | Layers=(64,32,16)"
            f" | n={len(X)}"
            f" | features={self.feature_count}"
            f" | CV-AUC={self.cv_score}"
        )
        return True

    def predict_proba(self, features):
        if not self.trained or self.model is None or self.scaler is None:
            return 0.5
        try:
            X = np.array(features, dtype=np.float32).reshape(1, -1)
            if self.feature_count and X.shape[1] != self.feature_count:
                print(f"[ML FAILURE] NN feature mismatch: expected {self.feature_count}, got {X.shape[1]} — advisory fallback")
                return 0.5
            X_s = self.scaler.transform(X)
            proba = self.model.predict_proba(X_s)[0]
            return round(float(proba[1]), 3)
        except Exception as e:
            print(f"⚠️  NN predict error: {e}")
            return 0.5

    def _scaled_vector(self, features):
        X = np.array(features, dtype=np.float32).reshape(1, -1)
        if self.scaler is None:
            return X[0]
        return self.scaler.transform(X)[0]

    def get_feature_contributions(self, features, feature_names=None, top_n=5):
        feature_names = feature_names or []
        if not self.trained or self.model is None:
            return {}
        try:
            scaled = self._scaled_vector(features)
            if hasattr(self.model, "coefs_") and self.model.coefs_:
                first_layer = np.abs(self.model.coefs_[0]).mean(axis=1)
                contrib = np.abs(scaled) * first_layer
            else:
                contrib = np.abs(scaled)

            names = feature_names or [f"f{i}" for i in range(len(contrib))]
            pairs = sorted(zip(names, contrib), key=lambda x: -float(x[1]))[:top_n]
            return {k: round(float(v), 4) for k, v in pairs}
        except Exception:
            return {}

    def get_feature_snapshot(self, features, feature_names=None):
        feature_names = feature_names or []
        try:
            values = np.array(features, dtype=np.float32).reshape(-1)
            names = feature_names or [f"f{i}" for i in range(len(values))]
            return {k: round(float(v), 4) for k, v in zip(names, values)}
        except Exception:
            return {}

    def get_stats(self):
        return {
            "trained": self.trained,
            "n_samples": self.n_samples,
            "cv_auc": self.cv_score,
            "layers": "(64,32,16)",
            "feature_count": self.feature_count,
        }


# =========================================
# SINGLETON
# =========================================


_nn_model = None


def get_nn_predictor() -> NeuralPredictor:
    global _nn_model
    if _nn_model is None:
        _nn_model = NeuralPredictor()
    return _nn_model


# =========================================
# TRAIN FROM DNA
# =========================================


def train_nn_from_dna():
    if not HAS_SKLEARN:
        return {"trained": False, "reason": "scikit-learn not installed — run: pip install scikit-learn"}

    try:
        from brain.trade_dna import load_trade_dna, get_ml_features
    except ImportError as e:
        return {"trained": False, "reason": f"Import error: {e}"}

    data = load_trade_dna()
    if len(data) < MIN_SAMPLES:
        return {"trained": False, "reason": f"Need {MIN_SAMPLES} trades, have {len(data)}"}

    X, y = [], []
    for rec in data:
        result = rec.get("result", "")
        if result not in ("WIN", "LOSS"):
            continue
        try:
            X.append(get_ml_features(rec))
            y.append(1 if result == "WIN" else 0)
        except Exception:
            continue

    if len(X) < MIN_SAMPLES:
        return {"trained": False, "reason": f"Valid samples: {len(X)}"}

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=int)

    nn = get_nn_predictor()
    ok = nn.train(X, y)

    return {
        "trained": ok,
        "n_samples": len(X),
        "cv_auc": nn.cv_score,
        "feature_count": int(X.shape[1]) if len(X.shape) > 1 else 0,
    }


# =========================================
# LIVE DIAGNOSTICS
# =========================================


def get_live_nn_diagnostics(features_array, feature_names=None, top_n=5):
    nn = get_nn_predictor()
    if not nn.trained:
        return {
            "top_features": {},
            "feature_snapshot": nn.get_feature_snapshot(features_array, feature_names),
            "feature_confidence": 0.0,
        }

    win_prob = nn.predict_proba(features_array)
    confidence = round(abs(win_prob - 0.5) * 200, 1)
    return {
        "top_features": nn.get_feature_contributions(features_array, feature_names, top_n=top_n),
        "feature_snapshot": nn.get_feature_snapshot(features_array, feature_names),
        "feature_confidence": confidence,
    }


# =========================================
# PREDICT
# =========================================


def nn_predict_win_prob(features_array, feature_names=None):
    nn = get_nn_predictor()
    win_prob = nn.predict_proba(features_array)
    model_conf = round(abs(win_prob - 0.5) * 200, 1)
    diagnostics = get_live_nn_diagnostics(features_array, feature_names)

    if not nn.trained:
        return {
            "win_prob": 0.5,
            "grade": "NEUTRAL",
            "boost": 0,
            "trained": False,
            "prediction": "NEUTRAL",
            "model_confidence": 0.0,
            "top_features": diagnostics.get("top_features", {}),
            "feature_snapshot": diagnostics.get("feature_snapshot", {}),
        }

    if win_prob >= 0.78:
        grade, boost = "EXCELLENT", 12
    elif win_prob >= 0.62:
        grade, boost = "GOOD", 6
    elif win_prob >= 0.50:
        grade, boost = "NEUTRAL", 0
    elif win_prob >= 0.38:
        grade, boost = "WEAK", -5
    else:
        grade, boost = "REJECT", -12

    print(
        f"🧠 NN | WIN_PROB={win_prob:.1%}"
        f" | Grade:{grade}"
        f" | Conf:{model_conf:.1f}"
        f" | Top:{diagnostics.get('top_features', {})}"
    )

    return {
        "win_prob": win_prob,
        "grade": grade,
        "boost": boost,
        "trained": True,
        "prediction": grade,
        "model_confidence": model_conf,
        "top_features": diagnostics.get("top_features", {}),
        "feature_snapshot": diagnostics.get("feature_snapshot", {}),
    }
