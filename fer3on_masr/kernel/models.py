from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketEngineReport:
    name: str
    bias: str
    confidence: float
    score: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TimeframeReport:
    timeframe: str
    trend: str
    confidence: float
    atr: float
    market_speed: float
    momentum: float
    support: float
    resistance: float
    liquidity: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CandlePrediction:
    label: str
    probability: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LiquidityProfile:
    buy_side: list[float]
    sell_side: list[float]
    traps: list[str]
    sweep_zones: list[float]
    best_target: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RangeForecast:
    expected_high: float
    expected_low: float
    expected_range: float
    expected_time: str
    expected_speed: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StrategyDecision:
    name: str
    action: str
    confidence: float
    weight: float
    risk_pct: float
    suggested_lot: float
    rationale: list[str]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionPlan:
    action: str
    confidence: float
    lot: float
    risk_pct: float
    selected_strategies: list[str]
    rejected_strategies: list[str]
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExplainabilityRecord:
    summary: str
    why_enter: list[str]
    why_exit: list[str]
    why_reject: list[str]
    factors: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
