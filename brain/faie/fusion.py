# =============================================================================
# FAIE — Evidence Fusion Engine (new addition, Volume 5 core)
# =============================================================================
# Combines evidence, not raw signals. Each analyst's evidence is first
# reduced to that analyst's own net_score, THEN the analysts are combined
# with configurable weights. This two-stage reduction means one analyst
# that produces five weak, agreeing pieces of evidence does not silently
# out-vote another analyst that produced one strong, decisive piece.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .analysts import AnalystReport
from .evidence import BULLISH, BEARISH, NEUTRAL

# Default relative weights. Sums to 1.0. Tunable without touching any
# existing engine — this is a governance parameter of the new layer only.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "MacroAnalyst": 0.09,
    "TechnicalAnalyst": 0.15,
    "SMCAnalyst": 0.19,
    "LiquidityAnalyst": 0.13,
    "VolumeAnalyst": 0.05,
    "PatternAnalyst": 0.09,
    "PsychologyAnalyst": 0.03,
    "RiskOfficer": 0.11,
    "ExecutionOfficer": 0.09,
    "SessionAnalyst": 0.07,
}


@dataclass
class FusedEvidence:
    net_score: float  # -100..100, positive = bullish lean
    dominant_direction: str
    per_analyst: Dict[str, float] = field(default_factory=dict)
    weights_used: Dict[str, float] = field(default_factory=dict)
    partial_analysts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "net_score": round(self.net_score, 2),
            "dominant_direction": self.dominant_direction,
            "per_analyst": {k: round(v, 2) for k, v in self.per_analyst.items()},
            "weights_used": self.weights_used,
            "partial_analysts": self.partial_analysts,
        }


class EvidenceFusionEngine:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(weights) if weights else dict(DEFAULT_WEIGHTS)

    def _analyst_net_score(self, report: AnalystReport) -> float:
        if not report.evidence:
            return 0.0
        return sum(e.weighted_score for e in report.evidence) / len(report.evidence)

    def fuse(self, reports: List[AnalystReport]) -> FusedEvidence:
        per_analyst: Dict[str, float] = {}
        partial: List[str] = []
        for r in reports:
            per_analyst[r.analyst] = self._analyst_net_score(r)
            if r.partial:
                partial.append(r.analyst)

        # Re-normalize weights over the analysts actually present, so a
        # missing/partial analyst doesn't silently zero out the total.
        present = [a for a in per_analyst if a not in partial]
        total_weight = sum(self.weights.get(a, 0.0) for a in present)
        weighted_sum = 0.0
        weights_used: Dict[str, float] = {}
        if total_weight > 0:
            for a in present:
                w = self.weights.get(a, 0.0) / total_weight
                weights_used[a] = round(w, 4)
                weighted_sum += per_analyst[a] * w

        if weighted_sum > 6:
            dominant = BULLISH
        elif weighted_sum < -6:
            dominant = BEARISH
        else:
            dominant = NEUTRAL

        return FusedEvidence(
            net_score=weighted_sum,
            dominant_direction=dominant,
            per_analyst=per_analyst,
            weights_used=weights_used,
            partial_analysts=partial,
        )
