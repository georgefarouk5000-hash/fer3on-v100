"""Adaptive micro-probe and execution flexibility layer."""

from __future__ import annotations

from typing import Any, Dict


SESSION_AGGRESSION_MULTIPLIERS = {
    "ASIA": 0.65,
    "LONDON": 1.15,
    "NEW_YORK": 1.25,
    "OVERLAP": 1.35,
    "NEWS_VOLATILITY": 0.55,
    "NEWS": 0.55,
    "SURVIVAL_MODE": 0.40,
    "SURVIVAL": 0.40,
}


def resolve_session_aggression_multiplier(session: str) -> float:
    session_key = str(session or "UNKNOWN").upper()
    if session_key in SESSION_AGGRESSION_MULTIPLIERS:
        return float(SESSION_AGGRESSION_MULTIPLIERS[session_key])
    if "OVERLAP" in session_key:
        return 1.35
    if "NEW" in session_key and "YORK" in session_key:
        return 1.25
    if session_key.startswith("LON"):
        return 1.15
    if session_key == "ASIA":
        return 0.65
    return 1.0


def build_execution_decision(
    spread: float,
    volatility: float,
    confidence: float,
    orderflow_pressure: float,
    smc_score: float,
    ai_override_strength: float,
    recovery_state: str = "NONE",
    session: str = "UNKNOWN",
    market_dna: str = "UNKNOWN",
    drawdown: float = 0.0,
    session_quality: float = 0.5,
    liquidity_quality: float = 0.5,
    counter_trend: bool = False,
) -> Dict[str, Any]:
    spread = max(0.0, float(spread))
    volatility = max(0.0, float(volatility))
    confidence = max(0.0, min(1.0, float(confidence)))
    orderflow_pressure = max(0.0, min(1.0, float(orderflow_pressure)))
    smc_score = max(0.0, min(100.0, float(smc_score)))
    ai_override_strength = max(0.0, min(1.0, float(ai_override_strength)))
    drawdown = max(0.0, float(drawdown))
    session_quality = max(0.0, min(1.0, float(session_quality)))
    liquidity_quality = max(0.0, min(1.0, float(liquidity_quality)))
    recovery = (recovery_state or "NONE").upper()
    market_dna = (market_dna or "UNKNOWN").upper()

    if recovery != "NONE" or drawdown > 0.10 or volatility > 2.2 or spread > 2.8:
        return {
            "decision": "SURVIVAL_HOLD",
            "probe_lot": 0.01,
            "scale_in_lot": 0.01,
            "risk_modifier": 0.35,
            "timing_pace": "cautious",
            "reasons": ["[MICRO_PROBE] survival or spread guard"],
        }

    strong_setup = (
        smc_score >= 80
        and confidence >= 0.65
        and orderflow_pressure >= 0.60
        and ai_override_strength >= 0.65
        and spread <= 2.5
        and volatility <= 1.8
        and session_quality >= 0.55
        and liquidity_quality >= 0.55
    )

    if strong_setup and confidence >= 0.80 and orderflow_pressure >= 0.75:
        return {
            "decision": "FULL_EXECUTION",
            "probe_lot": 0.02,
            "scale_in_lot": 0.03,
            "risk_modifier": 1.05,
            "timing_pace": "fast",
            "reasons": ["[AI_OVERRIDE] strong setup with high orderflow"],
        }

    if strong_setup or (counter_trend and smc_score >= 78 and confidence >= 0.68 and orderflow_pressure >= 0.60):
        probe_lot = 0.02 if counter_trend else 0.01
        return {
            "decision": "MICRO_PROBE",
            "probe_lot": probe_lot,
            "scale_in_lot": 0.02,
            "risk_modifier": 0.75,
            "timing_pace": "fast",
            "reasons": ["[MICRO_PROBE] probing momentum before full commitment"],
        }

    if confidence >= 0.55 and orderflow_pressure >= 0.45 and session_quality >= 0.55:
        return {
            "decision": "REDUCED_LOT",
            "probe_lot": 0.01,
            "scale_in_lot": 0.01,
            "risk_modifier": 0.65,
            "timing_pace": "balanced",
            "reasons": ["[SMART_REENTRY] reduced lot for cautious continuation"],
        }

    return {
        "decision": "WAIT",
        "probe_lot": 0.01,
        "scale_in_lot": 0.01,
        "risk_modifier": 0.45,
        "timing_pace": "cautious",
        "reasons": ["[MICRO_PROBE] insufficient edge for live entry"],
    }
