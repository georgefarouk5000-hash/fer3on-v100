import unittest

from core.meta_ai_orchestrator import MetaAIOrchestrator
from core.dynamic_aggression import evaluate_aggression_state
from core.adaptive_lot_engine import calculate_adaptive_lot
from core.contextual_memory import ContextualMemory


class AIEvolutionTests(unittest.TestCase):
    def test_orchestrator_uses_safe_bounds(self):
        orchestrator = MetaAIOrchestrator()
        result = orchestrator.orchestrate_intelligence(
            market_regime="RANGING",
            ai_confidence=0.82,
            volatility=0.8,
            spread=1.5,
            drawdown=0.03,
            session="LONDON",
            recovery_state="NONE",
            orderflow_pressure=0.2,
            market_dna="ALGORITHMIC_RANGING",
            execution_quality=0.9,
            recent_failures=0,
            winrate=0.58,
        )
        self.assertIn(result["final_strategy_mode"], {"SMC", "BALANCED", "SURVIVAL", "RECOVERY", "LIQUIDITY_HUNTER"})
        self.assertGreaterEqual(result["final_ai_override_strength"], 0.0)
        self.assertLessEqual(result["final_ai_override_strength"], 1.0)

    def test_aggression_reduces_in_danger(self):
        state = evaluate_aggression_state(
            volatility=2.4,
            drawdown=0.12,
            winrate=0.25,
            spread=3.2,
            session_quality=0.4,
            liquidity_quality=0.2,
            ai_confidence=0.35,
            recovery_state="ACTIVE",
            market_dna="LIQUIDITY_TRAP",
        )
        self.assertEqual(state["mode"], "SURVIVAL")
        self.assertLess(state["aggression_level"], 0.35)

    def test_lot_engine_scales_down_in_recovery(self):
        lot = calculate_adaptive_lot(
            balance=1000,
            ai_confidence=0.35,
            volatility=2.2,
            spread=2.1,
            drawdown=0.08,
            session="ASIA",
            market_dna="LIQUIDITY_TRAP",
            orderflow_pressure=0.8,
            recovery_state="ACTIVE",
            recent_performance=0.25,
        )
        self.assertGreaterEqual(lot, 0.01)
        self.assertLess(lot, 0.2)

    def test_contextual_memory_recall_and_update(self):
        memory = ContextualMemory(storage_path="tests/tmp_contextual_memory.json")
        memory.remember_episode(
            regime="RANGING",
            volatility=0.7,
            spread=1.2,
            liquidity_structure="SWEPT",
            session="LONDON",
            recovery_state="NONE",
            execution_quality=0.8,
            outcome="WIN",
            setup_type="SMC",
            notes="tight range",
        )
        recall = memory.weighted_recall(
            regime="RANGING",
            volatility=0.7,
            spread=1.2,
            liquidity_structure="SWEPT",
            session="LONDON",
            recovery_state="NONE",
            execution_quality=0.8,
        )
        self.assertGreaterEqual(recall["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
