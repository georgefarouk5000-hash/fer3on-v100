"""Closed-candle TSM CHOCH-retest strategy rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence


STRATEGY_ID = "TSM"
STRATEGY_VERSION = "tsm-choch-retest-0.3.0"
ATR_PERIOD = 14
MOMENTUM_LOOKBACK = 48
MAX_CHOCH_AGE_BARS = 8
RETEST_TOLERANCE_ATR = 0.25
CONFIRMATION_BODY_ATR = 0.10
MIN_CHOCH_SCORE = 0.70
CHOCH_CONTINUATION_SCORE = 0.70
STOP_BUFFER_ATR = 0.15
TARGET_BUFFER_ATR = 0.10
MIN_TARGET_RR = 1.20
SWING_LEFT_BARS = 3
SWING_RIGHT_BARS = 3
SWING_PROMINENCE_ATR = 1.0
SWING_PROMINENCE_WINDOW_BARS = 8
MAX_ENTRY_DISTANCE_ATR = 1.0


@dataclass(frozen=True)
class TSMCandidate:
    signal: str
    decision_bar_time: str
    entry_price: float
    stop_price: float
    target_price: float
    risk_distance: float
    reward_distance: float
    reward_risk: float
    atr_at_decision: float
    choch_level: float
    choch_bar_time: str
    retest_bar_time: str
    retest_low: float
    retest_high: float
    stop_anchor_time: str
    stop_anchor_price: float
    stop_selection_reason: str
    stop_prominence_atr: float
    target_source: str
    target_level: float
    next_target_price: float | None
    h1_bias: str
    d1_bias: str
    m5_timing_confirmed: bool
    momentum_return: float
    confirmation_body_atr: float

    @property
    def entry_conditions(self) -> list[str]:
        conditions = [
            "MOMENTUM_DIRECTION_CONFIRMED",
            "CLOSED_CHOCH_CONFIRMED",
            "SEPARATE_CHOCH_RETEST_CONFIRMED",
            "CLOSED_CANDLE_ACCEPTANCE_BEYOND_CHOCH",
            f"CONFIRMATION_BODY_AT_LEAST_{CONFIRMATION_BODY_ATR:.2f}_ATR",
        ]
        if self.m5_timing_confirmed:
            conditions.append("M5_CLOSED_CANDLE_TIMING_CONFIRMED")
        return conditions

    @property
    def entry_reason(self) -> str:
        return f"{STRATEGY_ID}: " + " + ".join(self.entry_conditions)

    def evidence(self) -> dict[str, Any]:
        return {
            "strategy_version": STRATEGY_VERSION,
            "timeframe": "M15",
            "decision_bar_time": self.decision_bar_time,
            "choch_bar_time": self.choch_bar_time,
            "retest_bar_time": self.retest_bar_time,
            "choch_level": self.choch_level,
            "signal": self.signal,
            "momentum_return": self.momentum_return,
            "momentum_lookback": MOMENTUM_LOOKBACK,
            "atr": self.atr_at_decision,
            "choch_score": CHOCH_CONTINUATION_SCORE,
            "confirmation_body_atr": self.confirmation_body_atr,
            "retest_low": self.retest_low,
            "retest_high": self.retest_high,
            "stop_anchor_time": self.stop_anchor_time,
            "stop_anchor_price": self.stop_anchor_price,
            "stop_selection_reason": self.stop_selection_reason,
            "stop_prominence_atr": self.stop_prominence_atr,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "target_source": self.target_source,
            "target_level": self.target_level,
            "next_target_price": self.next_target_price,
            "h1_bias": self.h1_bias,
            "d1_bias": self.d1_bias,
            "m5_timing_confirmed": self.m5_timing_confirmed,
            "risk_distance": self.risk_distance,
            "reward_risk": self.reward_risk,
        }


@dataclass(frozen=True)
class _Swing:
    index: int
    price: float
    kind: str
    label: str | None
    prominence_atr: float = 0.0


def _value(rate: Any, key: str) -> float:
    try:
        return float(rate[key])
    except (KeyError, TypeError, IndexError, ValueError):
        return float(getattr(rate, key))


def _time(rate: Any) -> str:
    try:
        raw = rate["time"]
    except (KeyError, TypeError, IndexError, ValueError):
        raw = getattr(rate, "time")
    if isinstance(raw, datetime):
        value = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return datetime.fromtimestamp(float(raw), timezone.utc).isoformat()


def _atr(rates: Sequence[Any], period: int = ATR_PERIOD) -> float:
    window = rates[-period:]
    ranges: list[float] = []
    for offset, rate in enumerate(window):
        high = _value(rate, "high")
        low = _value(rate, "low")
        if offset == 0:
            ranges.append(high - low)
        else:
            previous_close = _value(window[offset - 1], "close")
            ranges.append(
                max(high - low, abs(high - previous_close), abs(low - previous_close))
            )
    return sum(ranges) / len(ranges) if ranges else 0.0


def _swings(rates: Sequence[Any], left: int = 2, right: int = 2) -> list[_Swing]:
    raw: list[tuple[int, float, str]] = []
    for index in range(left, len(rates) - right):
        candle = rates[index]
        high = _value(candle, "high")
        low = _value(candle, "low")
        before = rates[index - left:index]
        after = rates[index + 1:index + right + 1]
        neighbors = list(before) + list(after)
        if all(high > _value(row, "high") for row in neighbors):
            raw.append((index, high, "HIGH"))
        if all(low < _value(row, "low") for row in neighbors):
            raw.append((index, low, "LOW"))
    raw.sort(key=lambda item: item[0])

    previous: dict[str, float] = {}
    labeled: list[_Swing] = []
    for index, price, kind in raw:
        prior_price = previous.get(kind)
        if prior_price is None:
            label = None
        elif kind == "HIGH":
            label = "HH" if price > prior_price else "LH"
        else:
            label = "HL" if price > prior_price else "LL"
        labeled.append(_Swing(index, price, kind, label))
        previous[kind] = price
    return labeled


def _target(
    rates: Sequence[Any],
    entry: float,
    stop: float,
    signal: str,
    atr_value: float,
    *,
    h1_rates: Sequence[Any] = (),
    d1_rates: Sequence[Any] = (),
) -> tuple[float, str, float, float | None] | None:
    """Choose the nearest viable confirmed opposing swing, not an RR-derived price."""
    candidates: list[tuple[float, str, float]] = []
    for timeframe, context_rates in (
        ("M15", rates),
        ("H1", h1_rates),
        ("D1", d1_rates),
    ):
        context_atr = _atr(context_rates)
        if context_atr <= 0:
            continue
        buffer = min(
            context_atr * TARGET_BUFFER_ATR,
            atr_value * 0.25,
        )
        for point in _major_swings(context_rates, context_atr):
            is_opposing_level = (
                point.kind == "HIGH" and point.price > entry
                if signal == "BUY"
                else point.kind == "LOW" and point.price < entry
            )
            if not is_opposing_level:
                continue
            target = point.price - buffer if signal == "BUY" else point.price + buffer
            target_is_ahead = target > entry if signal == "BUY" else target < entry
            if target_is_ahead:
                candidates.append((target, timeframe, point.price))

    if not candidates:
        return None

    risk = abs(entry - stop)
    if risk <= 0:
        return None
    ordered = sorted(
        candidates,
        key=lambda item: item[0] - entry
        if signal == "BUY"
        else entry - item[0],
    )
    viable = [
        item for item in ordered
        if abs(item[0] - entry) / risk >= MIN_TARGET_RR
    ]
    primary = viable[0] if viable else ordered[0]
    later_targets = [
        item for item in ordered
        if (
            item[0] > primary[0] + atr_value * 0.1
            if signal == "BUY"
            else item[0] < primary[0] - atr_value * 0.1
        )
    ]
    next_target = later_targets[0][0] if later_targets else None
    return primary[0], f"{primary[1]}_SWING", primary[2], next_target


def _major_swings(
    rates: Sequence[Any],
    atr_value: float,
    *,
    minimum_prominence_atr: float = SWING_PROMINENCE_ATR,
) -> list[_Swing]:
    if atr_value <= 0 or len(rates) < SWING_LEFT_BARS + SWING_RIGHT_BARS + 1:
        return []

    candidates = _swings(
        rates,
        left=SWING_LEFT_BARS,
        right=SWING_RIGHT_BARS,
    )
    significant: list[_Swing] = []
    for point in candidates:
        before = rates[max(0, point.index - SWING_PROMINENCE_WINDOW_BARS):point.index]
        after = rates[
            point.index + 1:
            min(len(rates), point.index + SWING_PROMINENCE_WINDOW_BARS + 1)
        ]
        if not before or not after:
            continue
        if point.kind == "HIGH":
            prominence = min(
                point.price - min(_value(row, "low") for row in before),
                point.price - min(_value(row, "low") for row in after),
            ) / atr_value
        else:
            prominence = min(
                max(_value(row, "high") for row in before) - point.price,
                max(_value(row, "high") for row in after) - point.price,
            ) / atr_value
        if prominence >= minimum_prominence_atr:
            significant.append(
                _Swing(
                    point.index,
                    point.price,
                    point.kind,
                    None,
                    prominence,
                )
            )

    previous_by_kind: dict[str, float] = {}
    labeled: list[_Swing] = []
    for point in significant:
        previous = previous_by_kind.get(point.kind)
        if previous is None:
            label = None
        elif point.kind == "HIGH":
            label = "HH" if point.price > previous else "LH"
        else:
            label = "HL" if point.price > previous else "LL"
        labeled.append(
            _Swing(
                point.index,
                point.price,
                point.kind,
                label,
                point.prominence_atr,
            )
        )
        previous_by_kind[point.kind] = point.price
    return labeled


def _stop_anchor(
    rates: Sequence[Any],
    signal: str,
    entry: float,
    atr_value: float,
) -> tuple[_Swing, str] | None:
    major = _major_swings(rates, atr_value)
    if signal == "BUY":
        eligible = [
            point for point in major
            if point.kind == "LOW" and point.price < entry
        ]
        selected = eligible[-1] if eligible else None
        reason = (
            "LAST_MAJOR_PROTECTED_HL"
            if selected is not None and selected.label == "HL"
            else "LAST_MAJOR_M15_LOW"
        )
    else:
        eligible = [
            point for point in major
            if point.kind == "HIGH" and point.price > entry
        ]
        selected = eligible[-1] if eligible else None
        reason = (
            "LAST_MAJOR_PROTECTED_LH"
            if selected is not None and selected.label == "LH"
            else "LAST_MAJOR_M15_HIGH"
        )
    return (selected, reason) if selected is not None else None


def _structure_bias(rates: Sequence[Any]) -> str:
    atr_value = _atr(rates)
    major = _major_swings(rates, atr_value)
    highs = [point for point in major if point.kind == "HIGH"]
    lows = [point for point in major if point.kind == "LOW"]
    if not highs or not lows:
        return "NEUTRAL"
    if highs[-1].label == "HH" and lows[-1].label == "HL":
        return "BUY"
    if highs[-1].label == "LH" and lows[-1].label == "LL":
        return "SELL"
    return "NEUTRAL"


def _m5_timing_confirms(rates: Sequence[Any], signal: str) -> bool:
    if len(rates) < 4:
        return False
    current = rates[-1]
    previous = rates[-4:-1]
    if signal == "BUY":
        return (
            _value(current, "close") > _value(current, "open")
            and _value(current, "close")
            > max(_value(row, "high") for row in previous)
        )
    return (
        _value(current, "close") < _value(current, "open")
        and _value(current, "close")
        < min(_value(row, "low") for row in previous)
    )


def build_tsm_candidate(
    closed_rates: Sequence[Any],
    *,
    buy_entry: float,
    sell_entry: float,
    m5_rates: Sequence[Any],
    h1_rates: Sequence[Any],
    d1_rates: Sequence[Any] = (),
) -> tuple[TSMCandidate | None, str]:
    """Evaluate closed M15 entries with required closed M5/H1 context."""
    if len(closed_rates) < max(MOMENTUM_LOOKBACK + 1, ATR_PERIOD + 12, 20):
        return None, "INSUFFICIENT_TSM_CHOCH_HISTORY"
    if len(m5_rates) < 4:
        return None, "TSM_M5_CONTEXT_INSUFFICIENT"
    if len(h1_rates) < 20:
        return None, "TSM_H1_CONTEXT_INSUFFICIENT"
    if buy_entry <= 0 or sell_entry <= 0:
        raise ValueError("Both executable quote prices must be positive")

    current = closed_rates[-1]
    current_atr = _atr(closed_rates)
    if current_atr <= 0:
        return None, "TSM_CHOCH_ATR_UNAVAILABLE"
    reference_close = _value(closed_rates[-1 - MOMENTUM_LOOKBACK], "close")
    momentum_return = _value(current, "close") / reference_close - 1.0
    momentum_side = "BUY" if momentum_return > 0 else "SELL" if momentum_return < 0 else None
    if momentum_side is None:
        return None, "TSM_FLAT_MOMENTUM"
    h1_bias = _structure_bias(h1_rates)
    d1_bias = _structure_bias(d1_rates) if d1_rates else "UNAVAILABLE"

    candidates: list[tuple[int, int, float]] = []
    first_choch = max(
        12,
        ATR_PERIOD + 2,
        len(closed_rates) - MAX_CHOCH_AGE_BARS - 3,
    )
    for choch_index in range(first_choch, len(closed_rates) - 2):
        prefix = closed_rates[:choch_index + 1]
        event_atr = _atr(prefix)
        if event_atr <= 0:
            continue
        structure = _swings(prefix)
        labels = [point.label for point in structure[-6:] if point.label]
        previous = prefix[-2]
        choch_events: list[tuple[str, float]] = []
        if "LL" in labels[-2:] and _value(prefix[-1], "close") > _value(previous, "high"):
            choch_events.append(("BUY", _value(previous, "high")))
        if "HH" in labels[-2:] and _value(prefix[-1], "close") < _value(previous, "low"):
            choch_events.append(("SELL", _value(previous, "low")))

        for side, level in choch_events:
            if side != momentum_side or CHOCH_CONTINUATION_SCORE < MIN_CHOCH_SCORE:
                continue
            last_retest = min(
                len(closed_rates) - 1,
                choch_index + 1 + MAX_CHOCH_AGE_BARS,
            )
            for retest_index in range(choch_index + 1, last_retest):
                retest = closed_rates[retest_index]
                tolerance = event_atr * RETEST_TOLERANCE_ATR
                touched = (
                    side == "BUY"
                    and _value(retest, "low") <= level + tolerance
                    and _value(retest, "close") >= level
                ) or (
                    side == "SELL"
                    and _value(retest, "high") >= level - tolerance
                    and _value(retest, "close") <= level
                )
                if touched:
                    candidates.append((choch_index, retest_index, level))
                    break

    if not candidates:
        return None, "TSM_WAITING_FOR_CHOCH_RETEST"

    choch_index, retest_index, choch_level = candidates[-1]
    side = momentum_side
    current_open = _value(current, "open")
    current_close = _value(current, "close")
    body_atr = abs(current_close - current_open) / current_atr
    accepted = (
        side == "BUY" and current_close > choch_level and current_close > current_open
    ) or (
        side == "SELL" and current_close < choch_level and current_close < current_open
    )
    if not accepted or body_atr < CONFIRMATION_BODY_ATR:
        return None, "TSM_CHOCH_RETEST_WAITING_ACCEPTANCE"

    entry = buy_entry if side == "BUY" else sell_entry
    if abs(entry - choch_level) > current_atr * MAX_ENTRY_DISTANCE_ATR:
        return None, "TSM_ENTRY_EXTENDED_FROM_CHOCH"
    m5_timing_confirmed = _m5_timing_confirms(m5_rates, side)
    if not m5_timing_confirmed:
        return None, "TSM_M5_TIMING_NOT_CONFIRMED"
    for timeframe, bias in (("H1", h1_bias), ("D1", d1_bias)):
        if bias in {"BUY", "SELL"} and bias != side:
            return None, f"TSM_HTF_BIAS_CONFLICT_{timeframe}_{bias}"

    stop_selection = _stop_anchor(closed_rates, side, entry, current_atr)
    if stop_selection is None:
        return None, "TSM_NO_MAJOR_M15_STOP_STRUCTURE"
    anchor, stop_selection_reason = stop_selection
    buffer = current_atr * STOP_BUFFER_ATR
    stop = anchor.price - buffer if side == "BUY" else anchor.price + buffer
    risk = abs(entry - stop)
    if risk <= 0:
        return None, "TSM_STRUCTURAL_STOP_GEOMETRY_INVALID"
    target_selection = _target(
        closed_rates,
        entry,
        stop,
        side,
        current_atr,
        h1_rates=h1_rates,
        d1_rates=d1_rates,
    )
    if target_selection is None:
        return None, "TSM_NO_CONFIRMED_STRUCTURAL_TARGET"
    target, target_source, target_level, next_target = target_selection
    reward = abs(target - entry)

    return (
        TSMCandidate(
            signal=side,
            decision_bar_time=_time(current),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            risk_distance=risk,
            reward_distance=reward,
            reward_risk=reward / risk,
            atr_at_decision=current_atr,
            choch_level=choch_level,
            choch_bar_time=_time(closed_rates[choch_index]),
            retest_bar_time=_time(closed_rates[retest_index]),
            retest_low=_value(closed_rates[retest_index], "low"),
            retest_high=_value(closed_rates[retest_index], "high"),
            stop_anchor_time=_time(closed_rates[anchor.index]),
            stop_anchor_price=anchor.price,
            stop_selection_reason=stop_selection_reason,
            stop_prominence_atr=anchor.prominence_atr,
            target_source=target_source,
            target_level=target_level,
            next_target_price=next_target,
            h1_bias=h1_bias,
            d1_bias=d1_bias,
            m5_timing_confirmed=m5_timing_confirmed,
            momentum_return=momentum_return,
            confirmation_body_atr=body_atr,
        ),
        "TSM_CHOCH_RETEST_CONFIRMED",
    )
