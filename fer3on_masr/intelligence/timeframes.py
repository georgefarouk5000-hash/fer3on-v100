from __future__ import annotations

from statistics import mean
from typing import Any

from fer3on_masr.kernel.models import TimeframeReport


class TimeframeIntelligence:
    DEFAULT_WINDOWS = {
        "M1": 8,
        "M5": 12,
        "M15": 20,
        "H1": 35,
        "H4": 60,
        "D1": 120,
        "W1": 200,
    }

    @staticmethod
    def _close(rate: Any) -> float:
        try:
            if isinstance(rate, dict):
                return float(rate.get("close", 0.0) or 0.0)
            return float(getattr(rate, "close", 0.0) or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _high(rate: Any) -> float:
        try:
            if isinstance(rate, dict):
                return float(rate.get("high", 0.0) or 0.0)
            return float(getattr(rate, "high", 0.0) or 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _low(rate: Any) -> float:
        try:
            if isinstance(rate, dict):
                return float(rate.get("low", 0.0) or 0.0)
            return float(getattr(rate, "low", 0.0) or 0.0)
        except Exception:
            return 0.0

    def analyze(self, rates: list[Any], configured_timeframes: tuple[str, ...]) -> list[TimeframeReport]:
        closes = [self._close(r) for r in rates or []]
        highs = [self._high(r) for r in rates or []]
        lows = [self._low(r) for r in rates or []]
        if not closes:
            closes = [1.0, 1.1, 1.2, 1.15, 1.3, 1.28, 1.35, 1.4]
            highs = [c + 0.05 for c in closes]
            lows = [c - 0.05 for c in closes]

        reports: list[TimeframeReport] = []
        for timeframe in configured_timeframes:
            window = self.DEFAULT_WINDOWS.get(timeframe, 20)
            c = closes[-window:] if len(closes) >= window else closes
            h = highs[-window:] if len(highs) >= window else highs
            l = lows[-window:] if len(lows) >= window else lows
            trend = "BUY" if c[-1] >= c[0] else "SELL"
            support = min(l)
            resistance = max(h)
            atr = mean([abs(x - y) for x, y in zip(h, l)]) if h and l else 0.0
            velocity = abs(c[-1] - c[0]) / max(len(c), 1)
            momentum = ((c[-1] - mean(c)) / max(mean(c), 1e-6)) * 100.0
            confidence = min(95.0, 50.0 + abs(momentum) + velocity * 100.0)
            reports.append(
                TimeframeReport(
                    timeframe=timeframe,
                    trend=trend,
                    confidence=round(confidence, 2),
                    atr=round(atr, 5),
                    market_speed=round(velocity, 5),
                    momentum=round(momentum, 4),
                    support=round(support, 5),
                    resistance=round(resistance, 5),
                    liquidity="BUY_SIDE" if trend == "BUY" else "SELL_SIDE",
                    details={
                        "swing_high": round(max(h), 5),
                        "swing_low": round(min(l), 5),
                        "range": round(max(h) - min(l), 5),
                    },
                )
            )
        return reports
