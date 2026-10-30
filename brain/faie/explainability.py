# =============================================================================
# FAIE — Explainability Service (Volume 8)
# =============================================================================
# Every Decision must have a Human Explanation and a Machine Explanation.
# This module never invents facts: it only narrates the Decision object
# that ChiefDecisionOfficer already produced.
# =============================================================================

from __future__ import annotations

from typing import Dict

from .chief_decision_officer import Decision


class ExplanationBuilder:
    def human_explanation(self, decision: Decision) -> str:
        top = decision.top_scenario
        lines = [
            decision.advisory_label,
            "",
            f"Leading scenario: {top.label} "
            f"(probability {top.probability * 100:.1f}%, confidence {decision.confidence:.1f}%).",
        ]

        if decision.rejected_scenarios:
            alt = decision.rejected_scenarios[0]
            lines.append(
                f"Next best alternative: {alt.label} (probability {alt.probability * 100:.1f}%)."
            )

        if decision.contradictions.conflicts:
            lines.append("")
            lines.append(f"Analyst disagreement detected ({len(decision.contradictions.conflicts)} conflict(s)):")
            for c in decision.contradictions.conflicts:
                lines.append(f"  - {c.description}")
        else:
            lines.append("")
            lines.append("No directional disagreement between analysts this cycle.")

        if decision.risk_notes:
            lines.append("")
            lines.append("Risk Officer notes:")
            for note in decision.risk_notes:
                lines.append(f"  - {note}")

        partial = decision.fused_evidence.partial_analysts
        if partial:
            lines.append("")
            lines.append(f"Running on partial data from: {', '.join(partial)} (see analyst notes).")

        return "\n".join(lines)

    def machine_explanation(self, decision: Decision) -> Dict:
        return decision.to_dict()
