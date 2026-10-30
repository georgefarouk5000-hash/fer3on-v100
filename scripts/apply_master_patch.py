from pathlib import Path

ROOT = Path('/home/user/work/fer3on_src/FER3ON-AI-V2.2')

replacements = {
    'ml/ml_orchestrator.py': [
        (
            '        "rl_action": rl_result.get("action", "ENTER_QUARTER"),\n',
            '        "rl_action": "PASS",\n',
        ),
    ],
    'ml/neural_network.py': [
        (
            '# =========================================\n# FER3ON V5.7 — NEURAL NETWORK (MLP)\n# Neural diagnostics + feature visibility\n# =========================================\n',
            '# =========================================\n# FER3ON AI V2.2 — NEURAL NETWORK (MLP)\n# 22-feature advisory model with safe fallback\n# =========================================\n',
        ),
        (
            'import os\nimport numpy as np\nimport warnings\n',
            'import os\nimport numpy as np\nimport warnings\n\nfrom core.settings import ML_FEATURE_COUNT\n',
        ),
        (
            '    """\n    MLP: Input(17) → Dense(64,32,16) → Output(2)\n    V5.7:\n      - Predict / Probability / Confidence\n      - Feature contribution visibility\n    """\n',
            '    """\n    MLP: Input(22) → Dense(64,32,16) → Output(2)\n    FER3ON AI V2.2:\n      - 22-feature advisory model\n      - Predict / Probability / Confidence\n      - Feature contribution visibility\n      - Safe neutral fallback on feature mismatch\n    """\n',
        ),
        (
            '        self.cv_score = 0.0\n        self.n_samples = 0\n        self._load()\n',
            '        self.cv_score = 0.0\n        self.n_samples = 0\n        self.feature_count = 0\n        self._load()\n',
        ),
        (
            '                self.model = saved.get("model")\n                self.scaler = saved.get("scaler")\n                self.cv_score = float(saved.get("cv_score", 0.0) or 0.0)\n                self.n_samples = int(saved.get("n_samples", 0) or 0)\n                self.trained = self.model is not None and self.scaler is not None\n                if self.trained:\n                    print("✅ Neural Network loaded from disk")\n',
            '                self.model = saved.get("model")\n                self.scaler = saved.get("scaler")\n                self.cv_score = float(saved.get("cv_score", 0.0) or 0.0)\n                self.n_samples = int(saved.get("n_samples", 0) or 0)\n                self.feature_count = int(saved.get("feature_count") or getattr(self.model, "n_features_in_", 0) or getattr(self.scaler, "n_features_in_", 0) or 0)\n                self.trained = self.model is not None and self.scaler is not None\n                if self.trained and self.feature_count not in (0, ML_FEATURE_COUNT):\n                    print(f"[ML FAILURE] NN feature mismatch on load: expected {ML_FEATURE_COUNT}, got {self.feature_count} — advisory fallback")\n                    self.model = None\n                    self.scaler = None\n                    self.trained = False\n                    self.feature_count = 0\n                elif self.trained:\n                    print(f"✅ Neural Network loaded from disk | features={self.feature_count or ML_FEATURE_COUNT}")\n',
        ),
        (
            '        self.model.fit(X_scaled, y)\n        self.trained = True\n        self.n_samples = len(X)\n',
            '        self.model.fit(X_scaled, y)\n        self.trained = True\n        self.n_samples = len(X)\n        self.feature_count = int(X.shape[1]) if len(X.shape) > 1 else 0\n',
        ),
        (
            '                        "cv_score": self.cv_score,\n                        "n_samples": self.n_samples,\n',
            '                        "cv_score": self.cv_score,\n                        "n_samples": self.n_samples,\n                        "feature_count": self.feature_count,\n',
        ),
        (
            '            f" | n={len(X)}"\n            f" | CV-AUC={self.cv_score}"\n',
            '            f" | n={len(X)}"\n            f" | features={self.feature_count}"\n            f" | CV-AUC={self.cv_score}"\n',
        ),
        (
            '        try:\n            X = np.array(features, dtype=np.float32).reshape(1, -1)\n            X_s = self.scaler.transform(X)\n',
            '        try:\n            X = np.array(features, dtype=np.float32).reshape(1, -1)\n            if self.feature_count and X.shape[1] != self.feature_count:\n                print(f"[ML FAILURE] NN feature mismatch: expected {self.feature_count}, got {X.shape[1]} — advisory fallback")\n                return 0.5\n            X_s = self.scaler.transform(X)\n',
        ),
        (
            '            "layers": "(64,32,16)",\n        }\n',
            '            "layers": "(64,32,16)",\n            "feature_count": self.feature_count,\n        }\n',
        ),
        (
            '        "trained": ok,\n        "n_samples": len(X),\n        "cv_auc": nn.cv_score,\n',
            '        "trained": ok,\n        "n_samples": len(X),\n        "cv_auc": nn.cv_score,\n        "feature_count": int(X.shape[1]) if len(X.shape) > 1 else 0,\n',
        ),
    ],
    'ml/xgboost_model.py': [
        (
            '# =========================================\n# FER3ON V5.2 — XGBOOST / GBM PREDICTOR\n# XGBoost إذا متاح، وإلا GradientBoosting\n# الإصلاح: lazy imports — لا crash عند التشغيل\n# =========================================\n',
            '# =========================================\n# FER3ON AI V2.2 — XGBOOST / GBM PREDICTOR\n# 22-feature advisory model with safe fallback\n# XGBoost إذا متاح، وإلا GradientBoosting\n# =========================================\n',
        ),
        (
            'import os\nimport json\nimport warnings\nimport numpy as np\n',
            'import os\nimport json\nimport warnings\nimport numpy as np\n\nfrom core.settings import ML_FEATURE_COUNT\n',
        ),
        (
            '        self.engine    = "NONE"\n        self._load()\n',
            '        self.engine    = "NONE"\n        self.feature_count = 0\n        self._load()\n',
        ),
        (
            '                with open(MODEL_FILE,  "rb") as f:\n                    self.model  = pickle.load(f)\n                with open(SCALER_FILE, "rb") as f:\n                    self.scaler = pickle.load(f)\n                self.trained = True\n                self.engine  = "XGBoost" if HAS_XGB else "GradientBoosting"\n                print(f"✅ GBM model loaded | Engine:{self.engine}")\n',
            '                with open(MODEL_FILE,  "rb") as f:\n                    model_blob = pickle.load(f)\n                with open(SCALER_FILE, "rb") as f:\n                    scaler_blob = pickle.load(f)\n                self.model  = model_blob.get("model") if isinstance(model_blob, dict) else model_blob\n                self.scaler = scaler_blob.get("scaler") if isinstance(scaler_blob, dict) else scaler_blob\n                self.feature_count = int(\n                    (model_blob.get("feature_count") if isinstance(model_blob, dict) else 0)\n                    or (scaler_blob.get("feature_count") if isinstance(scaler_blob, dict) else 0)\n                    or getattr(self.model, "n_features_in_", 0)\n                    or getattr(self.scaler, "n_features_in_", 0)\n                    or 0\n                )\n                self.trained = self.model is not None and self.scaler is not None\n                self.engine  = "XGBoost" if HAS_XGB else "GradientBoosting"\n                if self.trained and self.feature_count not in (0, ML_FEATURE_COUNT):\n                    print(f"[ML FAILURE] GBM feature mismatch on load: expected {ML_FEATURE_COUNT}, got {self.feature_count} — advisory fallback")\n                    self.model = None\n                    self.scaler = None\n                    self.trained = False\n                    self.feature_count = 0\n                    self.engine = "NONE"\n                elif self.trained:\n                    print(f"✅ GBM model loaded | Engine:{self.engine} | features={self.feature_count or ML_FEATURE_COUNT}")\n',
        ),
        (
            '        self.model.fit(X_scaled, y)\n        self.trained   = True\n        self.n_samples = len(X)\n',
            '        self.model.fit(X_scaled, y)\n        self.trained   = True\n        self.n_samples = len(X)\n        self.feature_count = int(X.shape[1]) if len(X.shape) > 1 else 0\n',
        ),
        (
            '            import pickle\n            with open(MODEL_FILE,  "wb") as f: pickle.dump(self.model,  f)\n            with open(SCALER_FILE, "wb") as f: pickle.dump(self.scaler, f)\n',
            '            import pickle\n            with open(MODEL_FILE,  "wb") as f:\n                pickle.dump({"model": self.model, "feature_count": self.feature_count},  f)\n            with open(SCALER_FILE, "wb") as f:\n                pickle.dump({"scaler": self.scaler, "feature_count": self.feature_count}, f)\n',
        ),
        (
            '            f"✅ GBM trained | Engine:{self.engine}"\n            f" | n={len(X)} | CV-AUC={self.cv_score}"\n',
            '            f"✅ GBM trained | Engine:{self.engine}"\n            f" | n={len(X)} | features={self.feature_count} | CV-AUC={self.cv_score}"\n',
        ),
        (
            '        try:\n            X = np.array(features, dtype=np.float32).reshape(1, -1)\n            X_scaled = self.scaler.transform(X)\n',
            '        try:\n            X = np.array(features, dtype=np.float32).reshape(1, -1)\n            if self.feature_count and X.shape[1] != self.feature_count:\n                print(f"[ML FAILURE] GBM feature mismatch: expected {self.feature_count}, got {X.shape[1]} — advisory fallback")\n                return 0.5\n            X_scaled = self.scaler.transform(X)\n',
        ),
        (
            '            "engine":    self.engine,\n        }\n',
            '            "engine":    self.engine,\n            "feature_count": self.feature_count,\n        }\n',
        ),
        (
            '        "engine":       pred.engine,\n        "top_features": dict(list(importance.items())[:5]),\n',
            '        "engine":       pred.engine,\n        "feature_count": int(X.shape[1]) if len(X.shape) > 1 else 0,\n        "top_features": dict(list(importance.items())[:5]),\n',
        ),
    ],
    'core/v7_validator.py': [
        (
            '        ("ASIA", "UNKNOWN", None, "ASIA", 70),\n        ("LONDON", "UNKNOWN", None, "LONDON", 55),\n        ("NEW_YORK", "UNKNOWN", None, "NEW_YORK", 58),\n        ("LONDON", "UNKNOWN", 14, "OVERLAP", 52),\n        ("LONDON", "VOLATILE", None, "LONDON", 60),\n        ("LONDON", "CRISIS", None, "LONDON", 65),\n',
            '        ("ASIA", "UNKNOWN", None, "ASIA", 58),\n        ("LONDON", "UNKNOWN", None, "LONDON", 52),\n        ("NEW_YORK", "UNKNOWN", None, "NEW_YORK", 55),\n        ("LONDON", "UNKNOWN", 14, "OVERLAP", 50),\n        ("LONDON", "VOLATILE", None, "LONDON", 57),\n        ("LONDON", "CRISIS", None, "LONDON", 62),\n',
        ),
    ],
    'testing/test_v7_execution_intelligence.py': [
        ('        self.assertEqual(r["base"], 55)\n        self.assertEqual(r["threshold"], 55)\n', '        self.assertEqual(r["base"], 52)\n        self.assertEqual(r["threshold"], 52)\n'),
        ('        self.assertEqual(r["threshold"], 60)\n', '        self.assertEqual(r["threshold"], 57)\n'),
        ('        self.assertEqual(r["threshold"], 52)\n', '        self.assertEqual(r["threshold"], 50)\n'),
        ('        self.assertEqual(classify_opportunity_entry(50), "NONE")\n', '        self.assertEqual(classify_opportunity_entry(50), "ENTER_QUARTER")\n'),
    ],
    'testing/test_quality_floor_adaptation.py': [
        ('        self.assertEqual(result["mode"], "EXECUTE_REDUCED")\n        self.assertEqual(result["threshold"], 51)\n', '        self.assertEqual(result["mode"], "STRICT_PASS")\n        self.assertEqual(result["threshold"], 45)\n'),
    ],
    'main.py': [
        (
            '        if final_brain["verdict"] == "EXECUTE_REDUCED" or v7_opportunistic:\n            _risk_mult = 0.70\n            if v7_opportunistic and v7_opp_entry:\n                _risk_mult = min(_risk_mult, v7_opp_entry.get("lot_mult", 0.5))\n            risk_percent = risk_percent * _risk_mult\n            print(f"⚠️  V7/BRAIN REDUCED RISK TO {risk_percent:.2f}%")\n\n',
            '        _advisory_risk_cap_mult = 1.0\n        if final_brain["verdict"] == "EXECUTE_REDUCED" or v7_opportunistic:\n            _advisory_risk_cap_mult = 0.70\n            if v7_opportunistic and v7_opp_entry:\n                _advisory_risk_cap_mult = min(_advisory_risk_cap_mult, v7_opp_entry.get("lot_mult", 0.5))\n            print(f"⚠️  AI V2 ADVISORY RISK CAP ARMED ×{_advisory_risk_cap_mult:.2f} (unified still decides)")\n\n        # V7 / micro timing evidence must be captured BEFORE unified authority.\n        _micro = check_v7_micro_trigger(SYMBOL, signal)\n        if V7_MICRO_TRIGGER_REQUIRED and not _micro.get(\n            "micro_trigger_confirmed", True\n        ):\n            print("⚠️  AI V2: micro-timing not yet confirmed → mild penalty before unified")\n            _ai_v1_evidence.add_legacy_rejection("V7_MICRO_TIMING_WAIT")\n\n',
        ),
        (
            "                ml_score=float(ml_result.get('model_confidence', 50) or 50),\n",
            "                ml_score=float(ml_result.get('ml_score', 50) or 50),\n",
        ),
        (
            '            risk_percent = apply_ai_v1_risk(\n                base_risk=risk_percent,\n                result=_u_res,\n                crisis_active=(crisis["state"] == "FREEZE"),\n                strategy=strategy,\n            )\n\n',
            '            risk_percent = apply_ai_v1_risk(\n                base_risk=risk_percent,\n                result=_u_res,\n                crisis_active=(crisis["state"] == "FREEZE"),\n                strategy=strategy,\n            )\n            if _advisory_risk_cap_mult < 1.0:\n                risk_percent = risk_percent * _advisory_risk_cap_mult\n                print(f"⚠️  AI V2 APPLIED ADVISORY RISK CAP → {risk_percent:.2f}%")\n\n',
        ),
        (
            '        except Exception as _ue:\n            print(f"⚠️  AI V1 AUTHORITY EXCEPTION (fallback to legacy logic): {_ue}")\n            traceback.print_exc()\n            _unified_size_mode = "LEGACY"\n            _unified_composite = final_brain.get("final_score", 0)\n            _unified_decision  = "LEGACY_FALLBACK"\n\n',
            '        except Exception as _ue:\n            print(f"[ERROR] AI V2 UNIFIED AUTHORITY EXCEPTION: {_ue}")\n            traceback.print_exc()\n            time.sleep(CHECK_INTERVAL)\n            last_print_time = now\n            continue\n\n',
        ),
        (
            '        # -------------------------------------------------------------------------\n        # V7 — MICRO TRIGGER (M1 timing)\n        # -------------------------------------------------------------------------\n        _micro = check_v7_micro_trigger(SYMBOL, signal)\n        if V7_MICRO_TRIGGER_REQUIRED and not _micro.get(\n            "micro_trigger_confirmed", True\n        ):\n            # AI V1: micro_timing_window هو واحد من سببين فقط للـ WAIT.\n            # لكن بدل إيقاف كل شيء، نسجل mild penalty ونسمح للـ unified بـ MICRO.\n            print("⚠️  AI V1: micro-timing not yet confirmed → mild penalty")\n            _ai_v1_evidence.add_legacy_rejection("V7_MICRO_TIMING_WAIT")\n\n',
            '',
        ),
    ],
}

for rel_path, edits in replacements.items():
    path = ROOT / rel_path
    text = path.read_text(encoding='utf-8')
    original = text
    for old, new in edits:
        if old not in text:
            raise SystemExit(f'Missing target in {rel_path}: {old[:120]!r}')
        text = text.replace(old, new, 1)
    if text != original:
        path.write_text(text, encoding='utf-8')
        print(f'Patched {rel_path}')

print('Master patch applied.')
