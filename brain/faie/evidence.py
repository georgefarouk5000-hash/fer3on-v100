# =============================================================================
# FAIE — Volume 5 primitive: Evidence + Evidence Graph
# =============================================================================
# An Evidence object is a single, attributable claim made by one analyst.
# It is NOT a decision. It carries a direction, a strength (how big the
# effect is) and a confidence (how sure the analyst is), kept separate on
# purpose — a strong but low-confidence read (e.g. an early liquidity sweep)
# must fuse differently than a weak but high-confidence one (e.g. a
# hard news blackout).
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"
VALID_DIRECTIONS = (BULLISH, BEARISH, NEUTRAL)

_SIGN = {BULLISH: 1.0, BEARISH: -1.0, NEUTRAL: 0.0}


@dataclass
class Evidence:
    analyst: str
    claim: str
    direction: str
    strength: float = 50.0        # 0-100: magnitude of the effect
    confidence: float = 50.0      # 0-100: analyst's certainty in the claim
    timeframe: str = "UNKNOWN"
    tags: List[str] = field(default_factory=list)
    source: str = "unknown"

    def __post_init__(self) -> None:
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Evidence.direction must be one of {VALID_DIRECTIONS}, got {self.direction!r}"
            )
        self.strength = max(0.0, min(100.0, float(self.strength)))
        self.confidence = max(0.0, min(100.0, float(self.confidence)))

    @property
    def weighted_score(self) -> float:
        """Signed contribution in [-100, 100]. BULLISH is positive."""
        return _SIGN[self.direction] * (self.strength / 100.0) * (self.confidence / 100.0) * 100.0

    def to_dict(self) -> Dict:
        return {
            "analyst": self.analyst,
            "claim": self.claim,
            "direction": self.direction,
            "strength": round(self.strength, 2),
            "confidence": round(self.confidence, 2),
            "timeframe": self.timeframe,
            "tags": list(self.tags),
            "source": self.source,
            "weighted_score": round(self.weighted_score, 2),
        }


@dataclass
class EvidenceGraph:
    """Flat, queryable collection of all Evidence produced this analysis cycle."""

    items: List[Evidence] = field(default_factory=list)

    def add(self, item: Evidence) -> None:
        self.items.append(item)

    def add_many(self, items: List[Evidence]) -> None:
        self.items.extend(items)

    def by_analyst(self, analyst: str) -> List[Evidence]:
        return [e for e in self.items if e.analyst == analyst]

    def by_direction(self, direction: str) -> List[Evidence]:
        return [e for e in self.items if e.direction == direction]

    def by_tag(self, tag: str) -> List[Evidence]:
        return [e for e in self.items if tag in e.tags]

    def net_score(self) -> float:
        """Simple unweighted average of all weighted_scores, in [-100, 100]."""
        if not self.items:
            return 0.0
        return sum(e.weighted_score for e in self.items) / len(self.items)

    def analysts(self) -> List[str]:
        seen: List[str] = []
        for e in self.items:
            if e.analyst not in seen:
                seen.append(e.analyst)
        return seen

    def to_dict(self) -> Dict:
        return {
            "count": len(self.items),
            "net_score": round(self.net_score(), 2),
            "items": [e.to_dict() for e in self.items],
        }
