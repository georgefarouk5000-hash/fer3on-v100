"""Adaptive execution engine for institutional-style execution modes."""

from __future__ import annotations

from typing import Any, Dict

from core.micro_probe_entries import build_execution_decision


def select_execution_mode(
    spread: float,
    volatility: float,
    confidence: float,
    orderflow_pressure: float,
    market_dna: str,
    recovery_state: str = "NONE",
    execution_latency: float = 0.0,
    session: str = "UNKNOWN",
    smc_score: float = 0.0,
    ai_override_strength: float = 0.0,
    counter_trend: bool = False,
    session_quality: float = 0.5,
    liquidity_quality: float = 0.5,
    drawdown: float = 0.0,
) -> Dict[str, Any]:
    spread = max(0.0, float(spread))
    volatility = max(0.0, float(volatility))
    confidence = max(0.0, min(1.0, float(confidence)))
    orderflow_pressure = max(0.0, min(1.0, float(orderflow_pressure)))
    market_dna = (market_dna or "UNKNOWN").upper()
    recovery = (recovery_state or "NONE").upper()

    decision = build_execution_decision(
        spread=spread,
        volatility=volatility,
        confidence=confidence,
        orderflow_pressure=orderflow_pressure,
        smc_score=smc_score,
        ai_override_strength=ai_override_strength,
        recovery_state=recovery,
        session=session,
        market_dna=market_dna,
        drawdown=drawdown,
        session_quality=session_quality,
        liquidity_quality=liquidity_quality,
        counter_trend=counter_trend,
    )

    decision_mode = decision["decision"]

    if decision_mode == "SURVIVAL_HOLD":
        mode = "Survival Hold"
        risk_modifier = 0.30
        timing_pace = "cautious"
    elif decision_mode == "MICRO_PROBE":
        mode = "Micro Probe Entry"
        risk_modifier = 0.72
        timing_pace = "fast"
    elif decision_mode == "REDUCED_LOT":
        mode = "Reduced Lot Entry"
        risk_modifier = 0.68
        timing_pace = "balanced"
    elif decision_mode == "WAIT":
        mode = "Waiting Entry"
        risk_modifier = 0.45
        timing_pace = "cautious"
    elif recovery != "NONE":
        mode = "Recovery Entry"
        risk_modifier = 0.55
        timing_pace = "slow"
    elif spread > 2.5 or volatility > 2.0:
        mode = "Volatility Compression Entry"
        risk_modifier = 0.70
        timing_pace = "slow"
    elif market_dna in {"LIQUIDITY_TRAP", "VOLATILITY_EXPANSION"}:
        mode = "Defensive Entry"
        risk_modifier = 0.60
        timing_pace = "cautious"
    elif confidence > 0.8 and orderflow_pressure > 0.7:
        mode = "Momentum Burst Entry"
        risk_modifier = 1.05
        timing_pace = "fast"
    elif confidence > 0.6 and orderflow_pressure > 0.4:
        mode = "Liquidity Sweep Entry"
        risk_modifier = 0.95
        timing_pace = "balanced"
    else:
        mode = "Precision Entry"
        risk_modifier = 0.85
        timing_pace = "balanced"

    if execution_latency > 0.2:
        risk_modifier *= 0.9

    risk_modifier *= float(decision.get("risk_modifier", 1.0))

    return {
        "mode": mode,
        "risk_modifier": round(max(0.15, min(1.35, risk_modifier)), 3),
        "timing_pace": timing_pace,
        "confidence": round(confidence, 3),
        "latency_safety": execution_latency <= 0.15,
        "execution_decision": decision_mode,
        "probe_lot": round(float(decision.get("probe_lot", 0.01)), 2),
        "scale_in_lot": round(float(decision.get("scale_in_lot", 0.01)), 2),
        "decision_reasons": decision.get("reasons", []),
    }
