"""Read-only grouped views over the compatibility settings module."""

from __future__ import annotations

from types import SimpleNamespace

from core import settings


def _group(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: getattr(settings, name) for name in names})


RISK = _group(
    "MAX_LOT", "MIN_LOT", "MAX_SL_DISTANCE_DOLLARS", "MAX_RISK_TOTAL",
    "RISK_PER_TRADE_PERCENT", "MAX_RISK_PER_DAY_PERCENT", "MAX_DAILY_LOSS_USD",
    "LOSS_PAUSE_ENABLED", "LOSS_PAUSE_TRIGGER",
)
EXECUTION = _group(
    "ORDER_RETRY_ON_STOPS_REJECTION_ENABLED", "ORDER_RETRY_MAX_ATTEMPTS",
    "ORDER_RETRY_MAX_WIDEN_FACTOR", "BROKER_STOP_LEVEL_FALLBACK",
)
SHADOW = _group(
    "PHASE2_RUNTIME_INFLUENCE", "PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED",
    "PHASE3_LIVE_AUTHORITY", "GENETIC_EVOLUTION_LIVE_INFLUENCE",
)
PHASES = _group(
    "PHASE2_ENTRY_CONTROLLER_ENABLED", "PHASE3_ENABLED",
    "PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED",
    "PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED",
)