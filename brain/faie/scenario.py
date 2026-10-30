# =============================================================================
# FAIE — Scenario Engine (new addition, Volume 5)
# =============================================================================
# Produces several ranked, mutually-exclusive scenarios instead of a single
# assumed outcome. Probabilities are derived from fused evidence plus a
# contradiction penalty (more internal disagreement -> flatter distribution,
# i.e. less confidence concentrated in one scenario), and always sum to 1.0.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .fusion import FusedEvidence
from .evidence import BULLISH, BEARISH, NEUTRAL

SCENARIO_LABELS = {
    BULLISH: "Bullish continuation / long bias",
    BEARISH: "Bearish continuation / short bias",
    NEUTRAL: "Range-bound / no clear edge",
}


@dataclass
class Scenario:
    label: str
    direction: str
    probability: float  # 0.0 - 1.0
    rationale: str

    def to_dict(self) -> Dict:
        return {
            "label": self.label,
            "direction": self.direction,
            "probability": round(self.probability, 4),
            "rationale": self.rationale,
        }


class ScenarioEngine:
    def build_scenarios(self, fused: FusedEvidence, contradiction_score: float) -> List[Scenario]:
        # Base pull toward the fused net_score, mapped from [-100,100] to a
        # bullish/bearish weight split, with a neutral baseline that grows
        # as contradiction_score grows (0 -> 20% neutral floor, 100 -> 60%).
        neutral_floor = 0.20 + 0.40 * (max(0.0, min(100.0, contradiction_score)) / 100.0)
        remaining = 1.0 - neutral_floor

        # net_score in [-100,100] -> bullish_share in [0,1]
        bullish_share = (fused.net_score + 100.0) / 200.0
        bullish_share = max(0.0, min(1.0, bullish_share))

        bullish_p = remaining * bullish_share
        bearish_p = remaining * (1.0 - bullish_share)
        neutral_p = neutral_floor

        scenarios = [
            Scenario(
                label=SCENARIO_LABELS[BULLISH], direction=BULLISH, probability=bullish_p,
                rationale=f"fused net_score={fused.net_score:.1f}, contradiction={contradiction_score:.1f}",
            ),
            Scenario(
                label=SCENARIO_LABELS[BEARISH], direction=BEARISH, probability=bearish_p,
                rationale=f"fused net_score={fused.net_score:.1f}, contradiction={contradiction_score:.1f}",
            ),
            Scenario(
                label=SCENARIO_LABELS[NEUTRAL], direction=NEUTRAL, probability=neutral_p,
                rationale=f"neutral floor grows with contradiction score ({contradiction_score:.1f})",
            ),
        ]
        scenarios.sort(key=lambda s: s.probability, reverse=True)
        return scenarios
