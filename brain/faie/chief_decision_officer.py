# =============================================================================
# FAIE — Chief Decision Officer (Volume 3 + Volume 5)
# =============================================================================
# Orchestrates: Analysts -> Evidence Fusion -> Contradiction Resolution ->
# Scenario ranking -> Decision.
#
# HARD RULE (Volume 1 Constitution): the Decision produced here is
# ADVISORY ONLY. This class contains no code path that sends, modifies,
# or cancels an order, and no code path that bypasses
# core.unified_decision / core.portfolio_risk_authority. It is designed to
# run ALONGSIDE the existing pipeline (shadow mode) during the paper-trading
# phase of the rollout (see docs/FAIE/ROADMAP.md, phases 7-8), producing an
# explainable second opinion that a human — or, later, the existing
# unified_decision gate — can compare against.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.unified_decision import DecisionContext

from .analysts import Analyst, AnalystReport, DEFAULT_ANALYSTS
from .evidence import Evidence, EvidenceGraph
from .fusion import EvidenceFusionEngine, FusedEvidence
from .contradiction import ContradictionResolver, ContradictionReport
from .scenario import ScenarioEngine, Scenario


@dataclass
class Decision:
    generated_at: str
    top_scenario: Scenario
    rejected_scenarios: List[Scenario]
    confidence: float  # 0-100, penalized by contradiction
    fused_evidence: FusedEvidence
    contradictions: ContradictionReport
    evidence_graph: EvidenceGraph
    analyst_reports: List[AnalystReport]
    risk_notes: List[str]
    advisory_label: str  # explicitly prefixed ADVISORY ONLY — see build below

    def to_dict(self) -> Dict:
        return {
            "generated_at": self.generated_at,
            "advisory_label": self.advisory_label,
            "confidence": round(self.confidence, 2),
            "top_scenario": self.top_scenario.to_dict(),
            "rejected_scenarios": [s.to_dict() for s in self.rejected_scenarios],
            "fused_evidence": self.fused_evidence.to_dict(),
            "contradictions": self.contradictions.to_dict(),
            "risk_notes": self.risk_notes,
            "evidence_graph": self.evidence_graph.to_dict(),
            "analyst_reports": [r.to_dict() for r in self.analyst_reports],
        }


class ChiefDecisionOfficer:
    def __init__(
        self,
        analysts: Optional[List[Analyst]] = None,
        fusion_weights: Optional[Dict[str, float]] = None,
    ):
        self.analysts = analysts if analysts is not None else list(DEFAULT_ANALYSTS)
        self.fusion_engine = EvidenceFusionEngine(weights=fusion_weights)
        self.contradiction_resolver = ContradictionResolver()
        self.scenario_engine = ScenarioEngine()

    def decide(self, ctx: DecisionContext) -> Decision:
        reports = [analyst.analyze(ctx) for analyst in self.analysts]

        graph = EvidenceGraph()
        for r in reports:
            graph.add_many(r.evidence)

        fused = self.fusion_engine.fuse(reports)
        contradictions = self.contradiction_resolver.resolve(reports)
        scenarios = self.scenario_engine.build_scenarios(fused, contradictions.contradiction_score)

        top = scenarios[0]
        rest = scenarios[1:]

        # Confidence = how much the top scenario leads, penalized by
        # contradiction. Never used to auto-execute — advisory only.
        second_best = rest[0].probability if rest else 0.0
        lead = max(0.0, top.probability - second_best)
        confidence = max(0.0, min(100.0, lead * 100.0))

        risk_notes = self._collect_risk_notes(reports)

        advisory_label = (
            f"ADVISORY ONLY — NOT AN EXECUTION SIGNAL: lean {top.direction} "
            f"({top.probability * 100:.1f}% scenario weight, confidence {confidence:.1f}). "
            "Must still clear core.unified_decision + Portfolio Risk Authority."
        )

        return Decision(
            generated_at=datetime.now(timezone.utc).isoformat(),
            top_scenario=top,
            rejected_scenarios=rest,
            confidence=confidence,
            fused_evidence=fused,
            contradictions=contradictions,
            evidence_graph=graph,
            analyst_reports=reports,
            risk_notes=risk_notes,
            advisory_label=advisory_label,
        )

    @staticmethod
    def _collect_risk_notes(reports: List[AnalystReport]) -> List[str]:
        notes: List[str] = []
        for r in reports:
            if r.analyst == "RiskOfficer" and r.notes:
                notes.append(r.notes)
            if r.evidence:
                for e in r.evidence:
                    if "hard_gate" in e.tags:
                        notes.append(e.claim)
        return notes
