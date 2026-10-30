from __future__ import annotations

from collections import defaultdict
from statistics import mean

from fer3on_masr.kernel.models import ExecutionPlan, StrategyDecision


class ExecutiveDirector:
    def decide(self, strategy_decisions: list[StrategyDecision]) -> ExecutionPlan:
        if not strategy_decisions:
            return ExecutionPlan(
                action="HOLD",
                confidence=0.0,
                lot=0.0,
                risk_pct=0.0,
                selected_strategies=[],
                rejected_strategies=[],
                reasons=["No strategies available"],
            )

        grouped: dict[str, list[StrategyDecision]] = defaultdict(list)
        for decision in strategy_decisions:
            grouped[decision.action].append(decision)

        action, winners = max(
            grouped.items(),
            key=lambda item: sum(d.confidence * d.weight for d in item[1]),
        )
        selected = [d.name for d in winners]
        rejected = [d.name for d in strategy_decisions if d.name not in selected]
        weighted_conf = sum(d.confidence * d.weight for d in winners) / max(sum(d.weight for d in winners), 1e-6)
        risk_pct = min(0.50, mean([d.risk_pct for d in winners]))
        lot = min(0.30, sum(d.suggested_lot for d in winners) / max(len(winners), 1))
        return ExecutionPlan(
            action=action,
            confidence=round(weighted_conf, 2),
            lot=round(lot, 4),
            risk_pct=round(risk_pct, 4),
            selected_strategies=selected,
            rejected_strategies=rejected,
            reasons=[f"Selected action {action} from {len(winners)} aligned strategies"],
            metadata={
                "all_strategies": [d.to_dict() for d in strategy_decisions],
            },
        )
