"""Synthetic orderflow intelligence for institutional-style decision support."""

from __future__ import annotations

from typing import Any, Dict


def analyze_orderflow(
    candle_velocity: float = 0.0,
    wick_aggression: float = 0.0,
    spread_behavior: float = 0.0,
    volume_expansion: float = 0.0,
    imbalance: float = 0.0,
    momentum_acceleration: float = 0.0,
) -> Dict[str, Any]:
    candle_velocity = max(-1.0, min(1.0, float(candle_velocity)))
    wick_aggression = max(0.0, min(1.0, float(wick_aggression)))
    spread_behavior = max(0.0, min(1.0, float(spread_behavior)))
    volume_expansion = max(0.0, min(1.0, float(volume_expansion)))
    imbalance = max(-1.0, min(1.0, float(imbalance)))
    momentum_acceleration = max(-1.0, min(1.0, float(momentum_acceleration)))

    if imbalance > 0.2 and momentum_acceleration > 0.2:
        bias = "BULLISH"
    elif imbalance < -0.2 and momentum_acceleration < -0.2:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    aggression_pressure = round(
        0.25 * abs(candle_velocity) + 0.25 * wick_aggression + 0.20 * volume_expansion + 0.15 * abs(momentum_acceleration) + 0.15 * spread_behavior,
        3,
    )
    exhaustion_probability = round(
        max(0.0, min(1.0, 0.25 * spread_behavior + 0.25 * abs(imbalance) + 0.25 * max(0.0, -momentum_acceleration) + 0.25 * (1 - volume_expansion))),
        3,
    )
    liquidity_trap_probability = round(
        max(0.0, min(1.0, 0.25 * wick_aggression + 0.25 * spread_behavior + 0.25 * max(0.0, -volume_expansion) + 0.25 * abs(imbalance))),
        3,
    )

    return {
        "orderflow_bias": bias,
        "aggression_pressure": aggression_pressure,
        "exhaustion_probability": exhaustion_probability,
        "liquidity_trap_probability": liquidity_trap_probability,
        "aggressive_buyer_pressure": max(0.0, imbalance),
        "aggressive_seller_pressure": max(0.0, -imbalance),
        "liquidity_vacuum": aggression_pressure > 0.7,
        "absorption_zones": wick_aggression > 0.6 and volume_expansion < 0.4,
        "exhaustion_detected": exhaustion_probability > 0.6,
        "iceberg_behavior_simulated": volume_expansion > 0.7 and spread_behavior > 0.5,
        "delta_pressure": round(imbalance + momentum_acceleration, 3),
        "stop_hunt_detected": wick_aggression > 0.7 and spread_behavior > 0.5,
        "sweep_velocity": round(abs(momentum_acceleration) + volume_expansion, 3),
        "tick_acceleration": round(abs(candle_velocity) + abs(momentum_acceleration), 3),
        "volume_shock_detected": volume_expansion > 0.75,
    }
