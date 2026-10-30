"""AI orchestration and confidence configuration."""

AI_CONFIG = {
    "confidence_floor": 0.55,
    "confidence_ceiling": 0.95,
    "memory_weight": 0.12,
    "rl_weight": 0.18,
    "xgboost_weight": 0.16,
    "orchestrator_weight": 0.20,
    "structure_weight": 0.14,
    "execution_weight": 0.10,
    "risk_weight": 0.10,
    "adaptation_cap": 0.12,
    "max_confidence_delta": 0.15,
}


def get_ai_config():
    return dict(AI_CONFIG)
