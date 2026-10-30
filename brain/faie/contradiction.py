# =============================================================================
# FAIE — Contradiction Resolver (new addition, Volume 5)
# =============================================================================
# Before a decision is allowed to look confident, this checks whether the
# analysts actually agree. It does not resolve conflicts by silently
# averaging them away (fusion already does that) — its job is to SURFACE
# the disagreement so the Chief Decision Officer's confidence and the
# human explanation both reflect it honestly.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import List

from .analysts import AnalystReport
from .evidence import BULLISH, BEARISH


@dataclass
class Conflict:
    analyst_a: str
    bias_a: str
    analyst_b: str
    bias_b: str
    description: str

    def to_dict(self):
        return {
            "analyst_a": self.analyst_a,
            "bias_a": self.bias_a,
            "analyst_b": self.analyst_b,
            "bias_b": self.bias_b,
            "description": self.description,
        }


@dataclass
class ContradictionReport:
    conflicts: List[Conflict] = field(default_factory=list)
    contradiction_score: float = 0.0  # 0-100, higher = more internal conflict
    pairs_checked: int = 0

    def to_dict(self):
        return {
            "contradiction_score": round(self.contradiction_score, 2),
            "pairs_checked": self.pairs_checked,
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


_OPPOSED = {(BULLISH, BEARISH), (BEARISH, BULLISH)}


class ContradictionResolver:
    def resolve(self, reports: List[AnalystReport]) -> ContradictionReport:
        # Only compare analysts that actually took a directional stance.
        directional = [r for r in reports if not r.partial and r.bias in (BULLISH, BEARISH)]
        conflicts: List[Conflict] = []
        pairs = list(combinations(directional, 2))
        for a, b in pairs:
            if (a.bias, b.bias) in _OPPOSED:
                conflicts.append(Conflict(
                    analyst_a=a.analyst, bias_a=a.bias,
                    analyst_b=b.analyst, bias_b=b.bias,
                    description=f"{a.analyst} reads {a.bias} while {b.analyst} reads {b.bias}",
                ))
        score = 0.0
        if pairs:
            score = 100.0 * (len(conflicts) / len(pairs))
        return ContradictionReport(conflicts=conflicts, contradiction_score=score, pairs_checked=len(pairs))
