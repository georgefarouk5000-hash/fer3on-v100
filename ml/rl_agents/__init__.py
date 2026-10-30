"""Distributed RL agent layer for FER3ON Phase 1 evolution."""

from __future__ import annotations

from typing import Any, Dict, List


class BaseRLAgent:
    """Minimal RL-style agent with bounded behavior and replay-like memory."""

    def __init__(self, name: str, reward_profile: str, aggression_profile: str) -> None:
        self.name = name
        self.reward_profile = reward_profile
        self.aggression_profile = aggression_profile
        self.memory_buffer: List[Dict[str, Any]] = []

    def encode_state(self, market_regime: str, session: str, volatility: float, confidence: float) -> Dict[str, Any]:
        return {
            "market_regime": (market_regime or "UNKNOWN").upper(),
            "session": (session or "UNKNOWN").upper(),
            "volatility": round(float(volatility), 3),
            "confidence": round(float(confidence), 3),
            "aggression_profile": self.aggression_profile,
        }

    def select_action(self, state: Dict[str, Any]) -> str:
        regime = str(state.get("market_regime", "UNKNOWN")).upper()
        confidence = float(state.get("confidence", 0.0))
        if regime == "TRENDING" and confidence > 0.7:
            return "ENTER"
        if regime == "RANGING" and confidence > 0.5:
            return "SCALE_IN"
        if regime == "EXPLOSIVE":
            return "WAIT"
        return "HOLD"

    def update(self, state: Dict[str, Any], action: str, reward: float) -> None:
        self.memory_buffer.append({"state": state, "action": action, "reward": reward})
        if len(self.memory_buffer) > 64:
            self.memory_buffer = self.memory_buffer[-64:]


class SwingRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="SwingRLAgent", reward_profile="trend_continuation_rr", aggression_profile="balanced")


class ScalpingRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="ScalpingRLAgent", reward_profile="momentum_liquidity", aggression_profile="aggressive")


class MicroRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="MicroRLAgent", reward_profile="microstructure_imbalance", aggression_profile="hyper")


class LiquidityRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="LiquidityRLAgent", reward_profile="sweep_reversal", aggression_profile="selective")


class RecoveryRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="RecoveryRLAgent", reward_profile="post_loss_stabilization", aggression_profile="defensive")


class SurvivalRLAgent(BaseRLAgent):
    def __init__(self) -> None:
        super().__init__(name="SurvivalRLAgent", reward_profile="catastrophic_protection", aggression_profile="survival")
