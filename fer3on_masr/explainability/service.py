from __future__ import annotations

from fer3on_masr.kernel.models import ExecutionPlan, ExplainabilityRecord, StrategyDecision


class ExplainabilityService:
    def build(self, plan: ExecutionPlan, decisions: list[StrategyDecision]) -> ExplainabilityRecord:
        why_enter = [f"{d.name} supported {d.action} with confidence {d.confidence}" for d in decisions if d.name in plan.selected_strategies]
        why_reject = [f"{d.name} was not selected because it disagreed or had lower weighted score" for d in decisions if d.name in plan.rejected_strategies]
        why_exit = [
            "Exit when confidence decays below governance threshold",
            "Exit when liquidity target is reached or market regime flips",
        ]
        summary = f"Executive Director selected {plan.action} at confidence {plan.confidence} with lot {plan.lot} and risk {plan.risk_pct}%"
        return ExplainabilityRecord(
            summary=summary,
            why_enter=why_enter,
            why_exit=why_exit,
            why_reject=why_reject,
            factors={
                "selected_strategies": plan.selected_strategies,
                "rejected_strategies": plan.rejected_strategies,
            },
        )
