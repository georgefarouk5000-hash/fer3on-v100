import unittest

from core.meta_ai_orchestrator import MetaAIOrchestrator
from core.micro_probe_entries import build_execution_decision
from core.recovery_cooldown import RecoveryCooldownTracker, PostTradeGateStateMachine, evaluate_reentry_gate
from core.dynamic_aggression import evaluate_aggression_state


class EvolutionLayerTests(unittest.TestCase):
    def test_probe_decision_uses_micro_entry_under_mixed_conditions(self):
        decision = build_execution_decision(
            spread=1.4,
            volatility=1.1,
            confidence=0.72,
            orderflow_pressure=0.64,
            smc_score=82,
            ai_override_strength=0.72,
            recovery_state="NONE",
            session="LONDON",
            market_dna="LIQUIDITY_SWEEP",
            drawdown=0.04,
            session_quality=0.8,
            liquidity_quality=0.7,
            counter_trend=False,
        )
        self.assertEqual(decision["decision"], "MICRO_PROBE")
        self.assertGreaterEqual(decision["probe_lot"], 0.01)

    def test_cooldown_reduces_reentry_after_loss(self):
        tracker = RecoveryCooldownTracker()
        state = tracker.record_outcome(
            outcome="LOSS",
            loss_amount=25.0,
            volatility=2.4,
            drawdown=0.08,
            session="NEW_YORK",
        )
        self.assertTrue(state["cooldown_active"])
        self.assertGreater(state["cooldown_seconds"], 0)

    def test_session_multiplier_reduces_aggression_in_news(self):
        state = evaluate_aggression_state(
            volatility=0.9,
            drawdown=0.02,
            winrate=0.55,
            spread=1.2,
            session_quality=0.8,
            liquidity_quality=0.8,
            ai_confidence=0.72,
            recovery_state="NONE",
            market_dna="TRENDING",
            session="NEWS_VOLATILITY",
        )
        self.assertLess(state["aggression_level"], 0.6)
        self.assertEqual(state["session_multiplier"], 0.55)

    def test_reentry_gate_requires_cooldown_pullback_and_structure(self):
        decision = evaluate_reentry_gate(
            previous_exit_time="2026-09-03T13:37:36+00:00",
            previous_exit_price=4474.63,
            current_price=4470.20,
            atr_value=5.0,
            profit_amount=11.78,
            direction="SELL",
            recent_closes=[4472.5, 4471.8, 4470.2],
            recent_highs=[4478.0, 4476.2, 4475.8],
            recent_lows=[4471.5, 4470.8, 4470.2],
            trend_bias="DOWN",
            liquidity_score=68,
            last_structure_signal="BEARISH",
            now="2026-09-03T13:47:36+00:00",
        )
        self.assertTrue(decision["allow"])
        self.assertEqual(decision["reason"], "REENTRY_OK")
        self.assertTrue(decision["pullback_detected"])

    def test_meta_orchestrator_blocks_trade_when_profit_reentry_gate_denies(self):
        orchestrator = MetaAIOrchestrator()
        result = orchestrator.orchestrate_intelligence(
            market_regime="TRENDING",
            ai_confidence=0.8,
            volatility=0.9,
            spread=1.2,
            drawdown=0.02,
            session="LONDON",
            recovery_state="NONE",
            orderflow_pressure=0.8,
            market_dna="TRENDING",
            execution_quality=0.8,
            recent_failures=0,
            winrate=0.6,
            signal="SELL",
            smc_score=86,
            candle_score=70,
            strategy="SMC",
            setup_type="BREAKDOWN",
            previous_exit_time="2026-09-03T13:37:36+00:00",
            previous_exit_price=4474.63,
            current_price=4478.20,
            atr_value=5.0,
            profit_amount=11.78,
            recent_closes=[4479.0, 4478.9, 4478.2],
            recent_highs=[4482.0, 4481.2, 4480.7],
            recent_lows=[4478.0, 4478.5, 4478.2],
            trend_bias="UP",
            liquidity_score=30,
            last_structure_signal="NEUTRAL",
        )
        self.assertFalse(result["execute_trade"])
        self.assertIsNotNone(result["reentry_gate"])
        self.assertFalse(result["reentry_gate"]["allow"])

    def test_post_trade_state_machine_sets_wait_allow_and_block(self):
        gate = PostTradeGateStateMachine()

        allow_case = gate.evaluate(
            outcome="PROFIT",
            previous_exit_time="2026-09-03T13:37:36+00:00",
            previous_exit_price=4474.63,
            current_price=4470.20,
            atr_value=5.0,
            profit_amount=11.78,
            direction="SELL",
            recent_closes=[4472.5, 4471.8, 4470.2],
            recent_highs=[4478.0, 4476.2, 4475.8],
            recent_lows=[4471.5, 4470.8, 4470.2],
            trend_bias="DOWN",
            liquidity_score=68,
            last_structure_signal="BEARISH",
            now="2026-09-03T13:47:36+00:00",
        )
        self.assertEqual(allow_case["state"], "ALLOW")
        self.assertTrue(allow_case["allow"])

        wait_case = gate.evaluate(
            outcome="PROFIT",
            previous_exit_time="2026-09-03T13:45:00+00:00",
            previous_exit_price=100.0,
            current_price=100.5,
            atr_value=5.0,
            profit_amount=12.0,
            direction="BUY",
            recent_closes=[99.8, 99.9, 100.5],
            recent_highs=[100.7, 100.8, 100.9],
            recent_lows=[99.2, 99.4, 99.8],
            trend_bias="UP",
            liquidity_score=60,
            last_structure_signal="BULLISH",
            now="2026-09-03T13:45:20+00:00",
        )
        self.assertEqual(wait_case["state"], "WAIT")
        self.assertFalse(wait_case["allow"])

        block_case = gate.evaluate(
            outcome="LOSS",
            previous_exit_time="2026-09-03T13:37:36+00:00",
            previous_exit_price=100.0,
            current_price=110.0,
            atr_value=1.0,
            profit_amount=-12.0,
            direction="BUY",
            recent_closes=[105.0, 109.0, 110.0],
            recent_highs=[110.0, 111.0, 112.0],
            recent_lows=[104.0, 108.0, 109.0],
            trend_bias="UP",
            liquidity_score=20,
            last_structure_signal="NEUTRAL",
            now="2026-09-03T13:47:36+00:00",
        )
        self.assertEqual(block_case["state"], "BLOCK")
        self.assertFalse(block_case["allow"])


if __name__ == "__main__":
    unittest.main()
