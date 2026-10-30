"""
Controlled meta-orchestration for FER3ON's AI evolution.

This module provides a bounded AI governance layer that blends
multiple intelligence systems while preserving execution stability,
risk safety and adaptive trading behavior.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.contextual_memory import ContextualMemory
from core.dynamic_aggression import resolve_session_aggression_multiplier
from core.micro_probe_entries import build_execution_decision
from core.recovery_cooldown import build_cooldown_state, evaluate_reentry_gate


class MetaAIOrchestrator:
    """Supreme AI coordination layer for Phase 1 evolution."""

    def __init__(self, memory: Optional[ContextualMemory] = None) -> None:
        self.memory = memory or ContextualMemory()

    def orchestrate_intelligence(
        self,
        market_regime: str = "UNKNOWN",
        ai_confidence: float = 0.5,
        volatility: float = 0.5,
        spread: float = 1.0,
        drawdown: float = 0.0,
        session: str = "UNKNOWN",
        recovery_state: str = "NONE",
        orderflow_pressure: float = 0.5,
        market_dna: str = "UNKNOWN",
        execution_quality: float = 0.5,
        recent_failures: int = 0,
        winrate: float = 0.5,
        signal: str = "BUY",
        smc_score: float = 0.0,
        candle_score: float = 0.0,
        liquidity_bias: str = "NEUTRAL",
        structure_bias: str = "NEUTRAL",
        strategy: str = "UNKNOWN",
        setup_type: str = "UNKNOWN",
        previous_exit_time: Any = None,
        previous_exit_price: float | None = None,
        current_price: float | None = None,
        atr_value: float | None = None,
        profit_amount: float = 0.0,
        recent_closes: Optional[list[float]] = None,
        recent_highs: Optional[list[float]] = None,
        recent_lows: Optional[list[float]] = None,
        trend_bias: str = "SIDEWAYS",
        liquidity_score: float = 0.0,
        last_structure_signal: str = "NEUTRAL",
    ) -> Dict[str, Any]:

        # =========================================================
        # NORMALIZATION
        # =========================================================

        regime = (market_regime or "UNKNOWN").upper()
        recovery = (recovery_state or "NONE").upper()
        signal = (signal or "NONE").upper()

        ai_confidence = max(0.0, min(1.0, float(ai_confidence)))
        volatility = max(0.0, float(volatility))
        spread = max(0.0, float(spread))
        drawdown = max(0.0, float(drawdown))
        orderflow_pressure = max(0.0, min(1.0, float(orderflow_pressure)))
        execution_quality = max(0.0, min(1.0, float(execution_quality)))
        winrate = max(0.0, min(1.0, float(winrate)))

        smc_score = max(0.0, min(100.0, float(smc_score)))
        candle_score = max(0.0, min(100.0, float(candle_score)))

        # =========================================================
        # AI AUTHORITY WEIGHTS
        # =========================================================

        authority_weights = {
            "neural_network": 0.20,
            "rl_agents": 0.22,
            "xgboost": 0.15,
            "memory_system": 0.10,
            "recovery_ai": 0.10,
            "orderflow_ai": 0.13,
            "market_regime_ai": 0.10,
        }

        # Trending
        if regime == "TRENDING":
            authority_weights["rl_agents"] += 0.08
            authority_weights["market_regime_ai"] += 0.05

        # Ranging
        elif regime == "RANGING":
            authority_weights["orderflow_ai"] += 0.08
            authority_weights["neural_network"] += 0.04

        # Explosive
        elif regime == "EXPLOSIVE":
            authority_weights["orderflow_ai"] += 0.12
            authority_weights["recovery_ai"] += 0.06

        # Recovery
        if recovery != "NONE":
            authority_weights["recovery_ai"] += 0.10
            authority_weights["memory_system"] += 0.05

        # High volatility
        if volatility > 1.5:
            authority_weights["orderflow_ai"] += 0.05

        # Failure adaptation
        if recent_failures > 2:
            authority_weights["memory_system"] += 0.05

        # Normalize
        total = sum(authority_weights.values())
        authority_weights = {
            k: round(v / total, 3)
            for k, v in authority_weights.items()
        }

        # =========================================================
        # STRATEGY MODE
        # =========================================================

        strategy_mode = "BALANCED"

        if recovery != "NONE":
            strategy_mode = "RECOVERY"

        elif regime == "TRENDING":
            strategy_mode = "SMC"

        elif regime == "RANGING":
            strategy_mode = "SMC"

        elif regime == "EXPLOSIVE":
            strategy_mode = "LIQUIDITY_HUNTER"

        if drawdown > 0.10:
            strategy_mode = "SURVIVAL"

        if recent_failures >= 3 and winrate < 0.35:
            strategy_mode = "SURVIVAL"

        # =========================================================
        # AI CONFIDENCE ENGINE
        # =========================================================

        confidence = ai_confidence

        # Positive factors
        confidence += (smc_score / 100.0) * 0.12
        confidence += (candle_score / 100.0) * 0.08
        confidence += orderflow_pressure * 0.08

        # Execution quality bonus
        if execution_quality > 0.8:
            confidence += 0.05

        # Recovery caution
        if recovery != "NONE":
            confidence -= 0.08

        # Spread penalty
        if spread > 2.5:
            confidence -= 0.08

        # Drawdown penalty
        if drawdown > 0.06:
            confidence -= 0.06

        confidence = max(0.05, min(0.98, confidence))

        # =========================================================
        # AI AGGRESSION ENGINE
        # =========================================================

        aggression = 0.45

        aggression += (confidence - 0.5) * 0.45
        aggression += (execution_quality - 0.5) * 0.25

        # Orderflow boost
        aggression += orderflow_pressure * 0.10

        # Strong SMC setups
        if smc_score > 75:
            aggression += 0.06

        # Strong candle confirmation
        if candle_score > 60:
            aggression += 0.05

        # Volatility reduction
        if volatility > 1.8:
            aggression -= 0.08

        # Dangerous spread
        if spread > 2.8:
            aggression -= 0.12

        # Recovery caution
        if recovery != "NONE":
            aggression -= 0.10

        # Survival suppression
        if strategy_mode == "SURVIVAL":
            aggression -= 0.15

        session_multiplier = resolve_session_aggression_multiplier(session)
        aggression *= session_multiplier

        cooldown_state = build_cooldown_state(
            recent_losses=max(0, int(recent_failures)),
            drawdown=drawdown,
            volatility=volatility,
            loss_amount=max(0.0, drawdown * 1000.0),
            session=session,
            recovery_state=recovery,
        )
        if cooldown_state["cooldown_active"]:
            aggression -= 0.08

        aggression = max(0.08, min(0.95, aggression))

        # =========================================================
        # DYNAMIC LOT MODIFIER
        # =========================================================

        lot_modifier = 1.0

        if strategy_mode == "SURVIVAL":
            lot_modifier = 0.35

        elif strategy_mode == "RECOVERY":
            lot_modifier = 0.45

        elif volatility > 2.0:
            lot_modifier = 0.70

        elif spread > 2.5:
            lot_modifier = 0.65

        elif confidence > 0.82:
            lot_modifier = 1.15

        elif confidence < 0.45:
            lot_modifier = 0.75

        # =========================================================
        # CONTEXTUAL MEMORY
        # =========================================================

        recall = self.memory.weighted_recall(
            regime=regime,
            volatility=volatility,
            spread=spread,
            liquidity_structure=market_dna,
            session=session,
            recovery_state=recovery,
            execution_quality=execution_quality,
            strategy=strategy,
            setup_type=setup_type,
        )

        # =========================================================
        # AI OVERRIDE LOGIC
        # =========================================================

        override_strength = 0.30

        override_strength += (confidence - 0.45) * 0.55
        override_strength += (smc_score / 100.0) * 0.15
        override_strength += orderflow_pressure * 0.10

        if cooldown_state["cooldown_active"]:
            override_strength -= 0.12

        # Allow counter-trend micro entries
        counter_trend = (
            signal == "BUY"
            and structure_bias == "SELL"
        ) or (
            signal == "SELL"
            and structure_bias == "BUY"
        )

        micro_entry_allowed = False

        if counter_trend:
            if (
                smc_score >= 78
                and confidence >= 0.68
                and orderflow_pressure >= 0.60
            ):
                micro_entry_allowed = True
                override_strength += 0.08

        ai_override_allowed = (
            smc_score >= 80
            and confidence >= 0.65
            and orderflow_pressure >= 0.60
            and spread <= 2.4
            and volatility <= 1.8
            and strategy_mode != "SURVIVAL"
            and not cooldown_state["cooldown_active"]
        )

        # Candle bypass system
        candle_bypass = False

        if (
            candle_score <= 5
            and smc_score >= 80
            and confidence >= 0.68
            and orderflow_pressure >= 0.60
        ):
            candle_bypass = True
            override_strength += 0.08

        if ai_override_allowed:
            override_strength += 0.10
            candle_bypass = True

        override_strength = max(0.10, min(0.95, override_strength))

        execution_decision = build_execution_decision(
            spread=spread,
            volatility=volatility,
            confidence=confidence,
            orderflow_pressure=orderflow_pressure,
            smc_score=smc_score,
            ai_override_strength=override_strength,
            recovery_state=recovery,
            session=session,
            market_dna=market_dna,
            drawdown=drawdown,
            counter_trend=counter_trend,
        )

        # =========================================================
        # FINAL DECISION
        # =========================================================

        execute_trade = False

        if confidence >= 0.60:
            execute_trade = True

        if candle_bypass or ai_override_allowed:
            execute_trade = True

        if micro_entry_allowed:
            execute_trade = True

        if execution_decision["decision"] == "SURVIVAL_HOLD":
            execute_trade = False

        if cooldown_state["cooldown_active"] and execution_decision["decision"] == "FULL_EXECUTION":
            execute_trade = False

        reentry_gate = None
        if previous_exit_time is not None or previous_exit_price is not None:
            reentry_gate = evaluate_reentry_gate(
                previous_exit_time=previous_exit_time,
                previous_exit_price=float(previous_exit_price) if previous_exit_price is not None else float(current_price or 0.0),
                current_price=float(current_price) if current_price is not None else float(spread or 0.0),
                atr_value=float(atr_value) if atr_value is not None else 0.0,
                profit_amount=float(profit_amount or 0.0),
                direction=signal,
                recent_closes=list(recent_closes or []),
                recent_highs=list(recent_highs or []),
                recent_lows=list(recent_lows or []),
                trend_bias=str(trend_bias or "SIDEWAYS").upper(),
                liquidity_score=float(liquidity_score or 0.0),
                last_structure_signal=str(last_structure_signal or "NEUTRAL").upper(),
            )
            if not reentry_gate["allow"]:
                execute_trade = False

        # =========================================================
        # RETURN
        # =========================================================

        return {
            "final_ai_signal": signal,
            "final_ai_confidence": round(confidence, 3),
            "final_execution_aggression": round(aggression, 3),
            "final_strategy_mode": strategy_mode,
            "final_recovery_state": recovery,
            "final_lot_modifier": round(lot_modifier, 3),
            "final_ai_override_strength": round(override_strength, 3),
            "authority_weights": authority_weights,
            "memory_recall": recall,
            "execute_trade": execute_trade,
            "micro_entry_allowed": micro_entry_allowed,
            "candle_bypass": candle_bypass,
            "execution_decision": execution_decision["decision"],
            "probe_lot": round(float(execution_decision.get("probe_lot", 0.01)), 2),
            "scale_in_lot": round(float(execution_decision.get("scale_in_lot", 0.01)), 2),
            "cooldown_active": cooldown_state["cooldown_active"],
            "cooldown_seconds": cooldown_state["cooldown_seconds"],
            "cooldown_reason": cooldown_state["cooldown_reason"],
            "reentry_gate": reentry_gate,
            "reentry_reason": reentry_gate["reason"] if reentry_gate else None,
            "session_multiplier": round(session_multiplier, 3),
            "reasoning": [
                f"regime={regime}",
                f"recovery={recovery}",
                f"strategy_mode={strategy_mode}",
                f"confidence={confidence:.2f}",
                f"aggression={aggression:.2f}",
                f"lot_modifier={lot_modifier:.2f}",
                f"override={override_strength:.2f}",
                f"micro_entry={micro_entry_allowed}",
                f"candle_bypass={candle_bypass}",
                f"[AI_OVERRIDE] decision={execution_decision['decision']}",
                f"[SESSION_AGGRESSION] multiplier={session_multiplier:.2f}",
                f"[RECOVERY_COOLDOWN] active={cooldown_state['cooldown_active']} reason={cooldown_state['cooldown_reason']}",
            ],
        }