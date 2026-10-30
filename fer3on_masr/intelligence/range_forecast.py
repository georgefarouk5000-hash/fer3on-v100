from __future__ import annotations

from typing import Any

from fer3on_masr.kernel.models import RangeForecast


class RangeIntelligence:
    def forecast(self, rates: list[Any], atr: float) -> RangeForecast:
        highs = []
        lows = []
        closes = []
        for rate in rates or []:
            if isinstance(rate, dict):
                highs.append(float(rate.get("high", 0.0) or 0.0))
                lows.append(float(rate.get("low", 0.0) or 0.0))
                closes.append(float(rate.get("close", 0.0) or 0.0))
            else:
                highs.append(float(getattr(rate, "high", 0.0) or 0.0))
                lows.append(float(getattr(rate, "low", 0.0) or 0.0))
                closes.append(float(getattr(rate, "close", 0.0) or 0.0))
        if not closes:
            closes = [1.0, 1.2, 1.3]
            highs = [1.05, 1.25, 1.35]
            lows = [0.95, 1.1, 1.2]
        anchor = closes[-1]
        atr = float(atr or 0.0) or max(max(highs) - min(lows), 0.1) / 3.0
        expected_high = anchor + atr
        expected_low = anchor - atr
        expected_range = expected_high - expected_low
        expected_time = "London" if atr > 1 else "Session Overlap"
        expected_speed = "FAST" if atr > 1 else "NORMAL"
        return RangeForecast(
            expected_high=round(expected_high, 5),
            expected_low=round(expected_low, 5),
            expected_range=round(expected_range, 5),
            expected_time=expected_time,
            expected_speed=expected_speed,
            details={"anchor": round(anchor, 5), "atr": round(atr, 5)},
        )
