from __future__ import annotations

from typing import Any, Sequence


def closed_rates_asof(
    rates: Sequence[Any],
    *,
    timeframe_seconds: int,
    decision_time: int,
) -> list[Any]:
    """Keep only candles fully closed by the shared decision timestamp."""
    if timeframe_seconds <= 0:
        raise ValueError("timeframe_seconds must be positive")

    closed = []
    for rate in rates:
        try:
            raw_time = rate["time"]
        except (KeyError, TypeError, IndexError, ValueError):
            try:
                raw_time = rate.time
            except AttributeError as exc:
                raise ValueError("Each rate must include a candle open time") from exc
        try:
            open_time = int(raw_time)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid candle open time: {raw_time!r}") from exc
        if open_time + timeframe_seconds <= decision_time:
            closed.append(rate)
    return closed
