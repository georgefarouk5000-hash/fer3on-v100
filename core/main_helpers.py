"""Pure helpers extracted from the runtime entrypoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def get_rate_value(rate: Any, field: str, default: Any = None) -> Any:
    if rate is None:
        return default
    try:
        if isinstance(rate, dict):
            return rate.get(field, default)
        value = getattr(rate, field, None)
        if value is not None:
            return value
        return rate[field]
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return default


def get_rate_close(rate: Any) -> float:
    if rate is None:
        return 0.0
    try:
        return float(get_rate_value(rate, "close", 0.0) or 0.0)
    except Exception:
        return 0.0


def rates_to_candles(rates: Any) -> list[dict[str, Any]]:
    candles = []
    for rate in rates if rates is not None else []:
        try:
            raw_time = get_rate_value(rate, "time")
            if raw_time is None:
                raw_time = get_rate_value(rate, "timestamp")
            try:
                candle_time = datetime.fromtimestamp(
                    float(raw_time), tz=timezone.utc
                ).isoformat()
            except (TypeError, ValueError, OSError, OverflowError):
                candle_time = str(raw_time or "")
            candles.append({
                "time": candle_time,
                "high": float(get_rate_value(rate, "high", 0) or 0),
                "low": float(get_rate_value(rate, "low", 0) or 0),
                "close": float(get_rate_value(rate, "close", 0) or 0),
            })
        except (TypeError, ValueError, OverflowError):
            continue
    return candles


def derive_signal(structure_bias: str, liquidity_bias: str) -> str:
    structure = str(structure_bias or "NEUTRAL").upper()
    liquidity = str(liquidity_bias or "NEUTRAL").upper()
    if structure in {"BUY", "SELL"}:
        return structure
    if liquidity in {"BUY", "SELL"}:
        return liquidity
    return "NONE"


def smc_strength_from_details(details: dict) -> float:
    grade_score = float(details.get("grade_score", 0) or 0)
    advanced_score = float(details.get("advanced_score", 0) or 0)
    conditions_met = float(details.get("conditions_met", 0) or 0)
    return round(min(9.0, max(grade_score / 10.0, advanced_score, conditions_met * 1.5)), 2)


def build_market_snapshot_hash(rates, atr, market_regime, session, confidence_pct):
    if rates is None:
        return None
    try:
        if len(rates) == 0:
            return None
    except TypeError:
        return None

    sample = rates[-5:] if len(rates) >= 5 else rates
    price_features = [round(get_rate_close(candle), 4) for candle in sample]
    return hash((
        tuple(price_features),
        round(float(atr or 0), 4),
        str(market_regime or "UNKNOWN"),
        str(session or "UNKNOWN"),
        round(float(confidence_pct or 0), 2),
    ))