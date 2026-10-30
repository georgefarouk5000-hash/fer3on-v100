"""Recovery intelligence V2 for post-loss stabilization."""

from __future__ import annotations

from typing import Any, Dict


def analyze_recovery_context(
    loss_amount: float = 0.0,
    spread: float = 0.0,
    liquidity_behavior: str = "NORMAL",
    timing_quality: float = 0.5,
    volatility_mismatch: float = 0.0,
    drawdown: float = 0.0,
    recent_winrate: float = 0.5,
) -> Dict[str, Any]:
    loss_amount = abs(float(loss_amount))
    spread = max(0.0, float(spread))
    timing_quality = max(0.0, min(1.0, float(timing_quality)))
    volatility_mismatch = max(0.0, min(1.0, float(volatility_mismatch)))
    drawdown = max(0.0, float(drawdown))
    recent_winrate = max(0.0, min(1.0, float(recent_winrate)))
    liquidity_behavior = (liquidity_behavior or "NORMAL").upper()

    failure_type = "NONE"
    if spread > 2.5:
        failure_type = "SPREAD_WIDE"
    elif liquidity_behavior in {"TRAP", "FAKE_BREAKOUT", "STOP_HUNT"}:
        failure_type = "LIQUIDITY_TRAP"
    elif timing_quality < 0.35:
        failure_type = "TIMING_MISMATCH"
    elif volatility_mismatch > 0.6:
        failure_type = "VOLATILITY_MISMATCH"
    elif drawdown > 0.08 or recent_winrate < 0.35:
        failure_type = "PERFORMANCE_DRAIN"

    if failure_type == "NONE":
        action = "WAIT"
        risk_modifier = 0.8
        explanation = "No clear recovery trigger; preserve capital"
    elif failure_type == "SPREAD_WIDE":
        action = "WAIT"
        risk_modifier = 0.5
        explanation = "Spread conditions unfavorable; hold and observe"
    elif failure_type == "LIQUIDITY_TRAP":
        action = "MICRO_REENTRY"
        risk_modifier = 0.4
        explanation = "Liquidity trap detected; micro re-entry only"
    elif failure_type == "TIMING_MISMATCH":
        action = "REDUCED_SIZE_REENTRY"
        risk_modifier = 0.55
        explanation = "Timing quality weak; use a controlled reduced-size re-entry"
    elif failure_type == "VOLATILITY_MISMATCH":
        action = "REDUCE_AGGRESSION"
        risk_modifier = 0.35
        explanation = "Volatility mismatch; compress aggression"
    else:
        action = "SURVIVAL_MODE"
        risk_modifier = 0.3
        explanation = "Recent performance weak; activate survival mode"

    if loss_amount > 20.0:
        action = "SURVIVAL_MODE"
        risk_modifier = 0.25

    return {
        "failure_type": failure_type,
        "action": action,
        "risk_modifier": round(risk_modifier, 3),
        "explanation": explanation,
        "loss_amount": round(loss_amount, 2),
    }
