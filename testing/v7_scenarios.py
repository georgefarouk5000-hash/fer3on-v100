from __future__ import annotations

from typing import Dict, List


class FakePosition:
    def __init__(self, position_type=0, price_open=1000.0, volume=0.01):
        self.type = position_type
        self.price_open = price_open
        self.volume = volume


def build_m1_candles(pattern: str = "mixed") -> List[Dict[str, float]]:
    if pattern == "rejection":
        return [
            {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "tick_volume": 120},
            {"open": 100.2, "high": 100.5, "low": 99.7, "close": 100.1, "tick_volume": 130},
            {"open": 100.1, "high": 100.6, "low": 99.6, "close": 100.3, "tick_volume": 140},
            {"open": 100.3, "high": 100.7, "low": 99.9, "close": 100.4, "tick_volume": 220},
            {"open": 100.4, "high": 100.8, "low": 99.7, "close": 100.6, "tick_volume": 260},
        ]
    if pattern == "micro_bos":
        return [
            {"open": 100.0, "high": 100.3, "low": 99.8, "close": 100.1, "tick_volume": 100},
            {"open": 100.1, "high": 100.4, "low": 99.9, "close": 100.2, "tick_volume": 110},
            {"open": 100.2, "high": 100.5, "low": 100.0, "close": 100.3, "tick_volume": 120},
            {"open": 100.3, "high": 100.7, "low": 100.1, "close": 100.4, "tick_volume": 130},
            {"open": 100.4, "high": 101.0, "low": 100.2, "close": 101.1, "tick_volume": 190},
        ]
    if pattern == "momentum":
        return [
            {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.1, "tick_volume": 80},
            {"open": 100.1, "high": 100.4, "low": 100.0, "close": 100.3, "tick_volume": 90},
            {"open": 100.3, "high": 100.6, "low": 100.2, "close": 100.5, "tick_volume": 110},
            {"open": 100.5, "high": 100.9, "low": 100.4, "close": 100.8, "tick_volume": 120},
            {"open": 100.8, "high": 101.3, "low": 100.7, "close": 101.1, "tick_volume": 180},
        ]
    if pattern == "volume":
        return [
            {"open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1, "tick_volume": 100},
            {"open": 100.1, "high": 100.3, "low": 100.0, "close": 100.2, "tick_volume": 110},
            {"open": 100.2, "high": 100.4, "low": 100.1, "close": 100.3, "tick_volume": 105},
            {"open": 100.3, "high": 100.5, "low": 100.2, "close": 100.4, "tick_volume": 112},
            {"open": 100.4, "high": 100.6, "low": 100.3, "close": 100.5, "tick_volume": 220},
        ]
    return [
        {"open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1, "tick_volume": 100},
        {"open": 100.1, "high": 100.3, "low": 100.0, "close": 100.2, "tick_volume": 110},
        {"open": 100.2, "high": 100.4, "low": 100.1, "close": 100.3, "tick_volume": 120},
        {"open": 100.3, "high": 100.5, "low": 100.2, "close": 100.4, "tick_volume": 130},
        {"open": 100.4, "high": 100.6, "low": 100.3, "close": 100.5, "tick_volume": 140},
    ]


def build_liquidity_vacuum_candles() -> List[Dict[str, float]]:
    return [
        {"open": 100.00, "high": 100.02, "low": 99.98, "close": 100.01},
        {"open": 100.01, "high": 100.03, "low": 99.99, "close": 100.02},
        {"open": 100.02, "high": 100.04, "low": 100.00, "close": 100.03},
        {"open": 100.03, "high": 100.05, "low": 100.01, "close": 100.04},
        {"open": 100.04, "high": 102.20, "low": 100.00, "close": 101.80},
    ]


def build_velocity_closes() -> List[float]:
    return [100.0, 100.4, 100.6, 100.9, 101.2, 101.8]
