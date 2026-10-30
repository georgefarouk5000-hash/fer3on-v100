"""Dynamic aggression engine for controlled AI evolution."""

from __future__ import annotations

from typing import Any, Dict

from core.micro_probe_entries import resolve_session_aggression_multiplier


def evaluate_aggression_state(
    volatility: float,
    drawdown: float,
    winrate: float,
    spread: float,
    session_quality: float,
    liquidity_quality: float,
    ai_confidence: float,
    recovery_state: str = "NONE",
    market_dna: str = "UNKNOWN",
    session: str = "UNKNOWN",
) -> Dict[str, Any]:
    volatility = max(0.0, float(volatility))
    drawdown = max(0.0, float(drawdown))
    winrate = max(0.0, min(1.0, float(winrate)))
    spread = max(0.0, float(spread))
    session_quality = max(0.0, min(1.0, float(session_quality)))
    liquidity_quality = max(0.0, min(1.0, float(liquidity_quality)))
    ai_confidence = max(0.0, min(1.0, float(ai_confidence)))
    recovery = (recovery_state or "NONE").upper()
    market_dna = (market_dna or "UNKNOWN").upper()
    session_key = (session or "UNKNOWN").upper()

    if recovery != "NONE" or drawdown > 0.10 or volatility > 2.0 or spread > 3.0 or winrate < 0.35:
        mode = "SURVIVAL"
        aggression_level = 0.15
        slow_execution = True
        increase_frequency = False
        disable_revenge = True
    elif market_dna in {"LIQUIDITY_TRAP", "VOLATILITY_EXPANSION", "EXHAUSTION"} or liquidity_quality < 0.3:
        mode = "DEFENSIVE"
        aggression_level = 0.28
        slow_execution = True
        increase_frequency = False
        disable_revenge = True
    elif ai_confidence > 0.8 and session_quality > 0.7 and liquidity_quality > 0.7 and winrate > 0.6:
        mode = "HUNTER"
        aggression_level = 0.72
        slow_execution = False
        increase_frequency = True
        disable_revenge = True
    elif ai_confidence > 0.6 and winrate > 0.45:
        mode = "AGGRESSIVE"
        aggression_level = 0.58
        slow_execution = False
        increase_frequency = True
        disable_revenge = True
    elif ai_confidence > 0.45:
        mode = "BALANCED"
        aggression_level = 0.45
        slow_execution = False
        increase_frequency = False
        disable_revenge = True
    else:
        mode = "DEFENSIVE"
        aggression_level = 0.32
        slow_execution = True
        increase_frequency = False
        disable_revenge = True

    if recovery == "ACTIVE":
        if mode == "SURVIVAL" or drawdown > 0.09 or volatility > 2.0 or spread > 3.0:
            mode = "SURVIVAL"
            aggression_level = min(aggression_level, 0.18)
        else:
            mode = "RECOVERY"
            aggression_level = min(aggression_level, 0.27)

    session_multiplier = resolve_session_aggression_multiplier(session_key)
    aggression_level = max(0.10, min(0.95, aggression_level * session_multiplier))

    trade_frequency_limiter = 1.0
    if drawdown > 0.08 or volatility > 2.0 or recovery != "NONE":
        trade_frequency_limiter = 0.45
    elif winrate < 0.35:
        trade_frequency_limiter = 0.55
    elif session_multiplier < 0.7:
        trade_frequency_limiter = 0.75
    elif spread > 2.5:
        trade_frequency_limiter = 0.8

    increase_execution_frequency = bool(increase_frequency and trade_frequency_limiter > 0.6 and not slow_execution)
    disable_revenge = bool(disable_revenge or recovery != "NONE" or drawdown > 0.05 or winrate < 0.38)

    return {
        "mode": mode,
        "aggression_level": round(aggression_level, 3),
        "slow_execution": slow_execution,
        "increase_execution_frequency": increase_execution_frequency,
        "disable_revenge": disable_revenge,
        "session_multiplier": round(session_multiplier, 3),
        "trade_frequency_limiter": round(trade_frequency_limiter, 3),
        "scale_in_modifier": round(min(1.0, max(0.25, session_multiplier * (0.9 if recovery != "NONE" else 1.0))), 3),
        "reason": f"mode={mode};vol={volatility:.2f};draw={drawdown:.2f};spread={spread:.2f};session={session_key}",
    }
