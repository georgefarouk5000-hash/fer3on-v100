"""Recovery cooldown and re-entry intelligence for FER3ON."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict
import time


def evaluate_reentry_gate(
    *,
    previous_exit_time,
    previous_exit_price,
    current_price,
    atr_value,
    profit_amount,
    direction,
    recent_closes,
    recent_highs,
    recent_lows,
    trend_bias,
    liquidity_score,
    last_structure_signal,
    now=None,
):
    """Evaluate whether a profitable trade can re-enter the market.

    Returns a structured decision with allow flag, reason, wait time, and
    supporting market-state metadata used by the execution pipeline.
    """
    if now is None:
        now_dt = datetime.now(timezone.utc)
    elif isinstance(now, str):
        try:
            now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        except ValueError:
            now_dt = datetime.now(timezone.utc)
    else:
        now_dt = now

    if previous_exit_time is None:
        return {
            "allow": True,
            "reason": "NO_PREVIOUS_EXIT",
            "wait_seconds": 0,
            "pullback_detected": False,
            "overextended": False,
        }

    if isinstance(previous_exit_time, str):
        try:
            previous_dt = datetime.fromisoformat(previous_exit_time.replace("Z", "+00:00"))
        except ValueError:
            previous_dt = datetime.now(timezone.utc)
    else:
        previous_dt = previous_exit_time

    elapsed_seconds = max(0.0, (now_dt - previous_dt).total_seconds())

    if abs(float(profit_amount)) < 2:
        min_wait = 30
    elif abs(float(profit_amount)) < 10:
        min_wait = 60
    else:
        min_wait = 90

    if atr_value is None or not isfinite(float(atr_value)) or float(atr_value) <= 0:
        extension = 0.0
        atr_window = 0.0
    else:
        extension = abs(float(current_price) - float(previous_exit_price)) / float(atr_value)
        atr_window = float(atr_value)

    if not recent_closes or len(recent_closes) < 2:
        pullback_detected = False
        small_tf_confirmation = False
    else:
        last_close = float(recent_closes[-1])
        prior_close = float(recent_closes[-2])
        exit_price = float(previous_exit_price)
        if direction == "BUY":
            pullback_detected = (
                last_close <= exit_price
                and prior_close <= exit_price
                and (last_close >= exit_price - max(atr_window, 1.0))
            ) or (last_close < exit_price and prior_close >= exit_price)
            small_tf_confirmation = (
                last_close > prior_close
                and last_close >= exit_price - max(atr_window * 0.5, 0.5)
            )
        else:
            pullback_detected = (
                last_close >= exit_price
                and prior_close >= exit_price
                and (last_close <= exit_price + max(atr_window, 1.0))
            ) or (last_close > exit_price and prior_close <= exit_price)
            small_tf_confirmation = (
                last_close < prior_close
                and last_close <= exit_price + max(atr_window * 0.5, 0.5)
            )

        if not pullback_detected and direction == "SELL":
            pullback_detected = (
                last_close <= exit_price
                and prior_close <= exit_price
                and abs(exit_price - last_close) <= max(atr_window, 1.0)
            )

        if not small_tf_confirmation and len(recent_closes) >= 3:
            third_close = float(recent_closes[-3])
            if direction == "BUY":
                small_tf_confirmation = last_close > third_close and last_close >= exit_price - max(atr_window * 0.7, 0.7)
            else:
                small_tf_confirmation = last_close < third_close and last_close <= exit_price + max(atr_window * 0.7, 0.7)

    overextended = extension > 1.1

    direction_ok = True
    if trend_bias == "UP" and direction == "SELL":
        direction_ok = False
    if trend_bias == "DOWN" and direction == "BUY":
        direction_ok = False

    structure_ok = last_structure_signal in {"BULLISH", "BEARISH"} and float(liquidity_score) >= 50

    if elapsed_seconds < min_wait:
        return {
            "allow": False,
            "reason": "POST_TRADE_CONFIRMATION_REQUIRED",
            "wait_seconds": int(min_wait - elapsed_seconds),
            "pullback_detected": pullback_detected,
            "overextended": overextended,
        }

    if overextended:
        return {
            "allow": False,
            "reason": "PRICE_OVEREXTENDED",
            "wait_seconds": int(min_wait),
            "pullback_detected": pullback_detected,
            "overextended": True,
        }

    if not small_tf_confirmation:
        return {
            "allow": False,
            "reason": "SMALL_TF_CONFIRMATION_REQUIRED",
            "wait_seconds": int(max(30, min_wait // 2)),
            "pullback_detected": pullback_detected,
            "overextended": overextended,
        }

    if not pullback_detected:
        return {
            "allow": False,
            "reason": "NO_VALID_PULLBACK",
            "wait_seconds": int(max(30, min_wait // 2)),
            "pullback_detected": False,
            "overextended": overextended,
        }

    if not direction_ok:
        return {
            "allow": False,
            "reason": "TREND_CONFLICT",
            "wait_seconds": int(min_wait // 2),
            "pullback_detected": pullback_detected,
            "overextended": overextended,
        }

    if not structure_ok:
        return {
            "allow": False,
            "reason": "STRUCTURE_NOT_CONFIRMED",
            "wait_seconds": int(min_wait // 2),
            "pullback_detected": pullback_detected,
            "overextended": overextended,
        }

    return {
        "allow": True,
        "reason": "REENTRY_OK",
        "wait_seconds": 0,
        "pullback_detected": True,
        "overextended": False,
    }


def build_cooldown_state(
    recent_losses: int = 0,
    drawdown: float = 0.0,
    volatility: float = 0.0,
    loss_amount: float = 0.0,
    session: str = "UNKNOWN",
    recovery_state: str = "NONE",
    now: float | None = None,
) -> Dict[str, Any]:
    now_ts = float(now if now is not None else time.time())
    recovery = (recovery_state or "NONE").upper()
    session_key = (session or "UNKNOWN").upper()

    cooldown_seconds = 0
    reason = "NONE"

    if recovery != "NONE" or drawdown > 0.08 or volatility > 2.0 or loss_amount > 10.0:
        if volatility > 2.4:
            cooldown_seconds = 180
            reason = "VOLATILITY_SPIKE"
        elif recent_losses >= 2:
            cooldown_seconds = 120
            reason = "CONSECUTIVE_LOSSES"
        elif drawdown > 0.08:
            cooldown_seconds = 120
            reason = "DRAWDOWN_RECOVERY"
        elif loss_amount > 20.0:
            cooldown_seconds = 120
            reason = "NORMAL_STOP_LOSS"
        else:
            cooldown_seconds = 60
            reason = "SMALL_LOSS"

    if session_key in {"NEWS_VOLATILITY", "NEWS"} and cooldown_seconds > 0:
        cooldown_seconds = max(cooldown_seconds, 600)

    if cooldown_seconds > 0:
        cooldown_active = True
        cooldown_until = now_ts + cooldown_seconds
        reentry_ready = False
    else:
        cooldown_active = False
        cooldown_until = 0.0
        reentry_ready = True

    return {
        "cooldown_active": cooldown_active,
        "cooldown_seconds": int(cooldown_seconds),
        "cooldown_reason": reason,
        "cooldown_until": cooldown_until,
        "reentry_ready": reentry_ready,
        "analysis_only": cooldown_active,
        "reentry_mode": "SMART_REENTRY" if reentry_ready else "COOLDOWN",
    }


class PostTradeGateStateMachine:
    """State machine for post-trade re-entry gating using confirmation logic.

    States:
      - ALLOW: the trade is allowed to re-enter
      - WAIT: short soft-cooldown still active; market needs confirmation
      - BLOCK: guard conditions prevent re-entry
    """

    def __init__(self) -> None:
        self.log: list[Dict[str, Any]] = []

    def evaluate(
        self,
        *,
        outcome,
        previous_exit_time,
        previous_exit_price,
        current_price,
        atr_value,
        profit_amount,
        direction,
        recent_closes,
        recent_highs,
        recent_lows,
        trend_bias,
        liquidity_score,
        last_structure_signal,
        now=None,
    ) -> Dict[str, Any]:
        decision = evaluate_reentry_gate(
            previous_exit_time=previous_exit_time,
            previous_exit_price=previous_exit_price,
            current_price=current_price,
            atr_value=atr_value,
            profit_amount=profit_amount,
            direction=direction,
            recent_closes=recent_closes,
            recent_highs=recent_highs,
            recent_lows=recent_lows,
            trend_bias=trend_bias,
            liquidity_score=liquidity_score,
            last_structure_signal=last_structure_signal,
            now=now,
        )

        if decision["allow"]:
            state = "ALLOW"
        elif decision["reason"] in {"POST_TRADE_CONFIRMATION_REQUIRED", "SMALL_TF_CONFIRMATION_REQUIRED", "NO_VALID_PULLBACK"}:
            state = "WAIT"
        else:
            state = "BLOCK"

        record = {
            "outcome": str(outcome or "UNKNOWN").upper(),
            "state": state,
            "allow": bool(decision["allow"]),
            "reason": decision["reason"],
            "wait_seconds": int(decision.get("wait_seconds", 0) or 0),
            "pullback_detected": bool(decision.get("pullback_detected", False)),
            "overextended": bool(decision.get("overextended", False)),
            "timestamp": now if now is not None else datetime.now(timezone.utc),
        }
        self.log.append(record)
        return record


class RecoveryCooldownTracker:
    def __init__(self) -> None:
        self._cooldown_until = 0.0
        self._consecutive_losses = 0
        self._last_exit_time = None
        self._last_exit_price = None
        self._last_exit_direction = None
        self._last_profit_amount = 0.0
        self._last_reentry_decision = None
        self._decision_log: list[Dict[str, Any]] = []

    def register_exit(
        self,
        *,
        exit_time,
        exit_price,
        direction,
        profit_amount,
        now: float | str | datetime | None = None,
    ) -> Dict[str, Any]:
        self._last_exit_time = exit_time
        self._last_exit_price = float(exit_price)
        self._last_exit_direction = str(direction).upper()
        self._last_profit_amount = float(profit_amount)

        if now is None:
            now_dt = datetime.now(timezone.utc)
        elif isinstance(now, str):
            try:
                now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
            except ValueError:
                now_dt = datetime.now(timezone.utc)
        else:
            now_dt = now

        return {
            "last_exit_time": self._last_exit_time,
            "last_exit_price": self._last_exit_price,
            "last_exit_direction": self._last_exit_direction,
            "last_profit_amount": self._last_profit_amount,
            "registered_at": now_dt,
        }

    def evaluate_profit_reentry(
        self,
        *,
        current_price,
        atr_value,
        direction=None,
        recent_closes,
        recent_highs,
        recent_lows,
        trend_bias,
        liquidity_score,
        last_structure_signal,
        now=None,
    ) -> Dict[str, Any]:
        side = (direction or self._last_exit_direction or "BUY").upper()
        if self._last_exit_time is None:
            decision = {
                "allow": True,
                "reason": "NO_PREVIOUS_EXIT",
                "wait_seconds": 0,
                "pullback_detected": False,
                "overextended": False,
            }
        else:
            decision = evaluate_reentry_gate(
                previous_exit_time=self._last_exit_time,
                previous_exit_price=self._last_exit_price,
                current_price=current_price,
                atr_value=atr_value,
                profit_amount=self._last_profit_amount,
                direction=side,
                recent_closes=recent_closes,
                recent_highs=recent_highs,
                recent_lows=recent_lows,
                trend_bias=trend_bias,
                liquidity_score=liquidity_score,
                last_structure_signal=last_structure_signal,
                now=now,
            )

        self._last_reentry_decision = {
            "decision": decision,
            "direction": side,
            "current_price": float(current_price),
            "timestamp": now if now is not None else datetime.now(timezone.utc),
        }
        self._decision_log.append(self._last_reentry_decision)
        return decision

    def get_last_reentry_decision(self) -> Dict[str, Any] | None:
        return self._last_reentry_decision

    def get_decision_log(self) -> list[Dict[str, Any]]:
        return list(self._decision_log)

    def record_outcome(
        self,
        outcome: str,
        loss_amount: float = 0.0,
        volatility: float = 0.0,
        drawdown: float = 0.0,
        session: str = "UNKNOWN",
        now: float | None = None,
    ) -> Dict[str, Any]:
        outcome = (outcome or "").upper()
        now_ts = float(now if now is not None else time.time())

        if outcome in {"LOSS", "LOSE", "LOST", "LOSS_TRADE"}:
            self._consecutive_losses += 1
            state = build_cooldown_state(
                recent_losses=self._consecutive_losses,
                drawdown=drawdown,
                volatility=volatility,
                loss_amount=loss_amount,
                session=session,
                recovery_state="ACTIVE",
                now=now_ts,
            )
            self._cooldown_until = state["cooldown_until"]
        else:
            self._consecutive_losses = max(0, self._consecutive_losses - 1)
            state = build_cooldown_state(
                recent_losses=self._consecutive_losses,
                drawdown=drawdown,
                volatility=volatility,
                loss_amount=loss_amount,
                session=session,
                recovery_state="NONE",
                now=now_ts,
            )
            self._cooldown_until = 0.0

        state["consecutive_losses"] = self._consecutive_losses
        return state

    def get_state(self, now: float | None = None) -> Dict[str, Any]:
        now_ts = float(now if now is not None else time.time())
        cooldown_active = now_ts < self._cooldown_until
        return {
            "cooldown_active": cooldown_active,
            "cooldown_until": self._cooldown_until,
            "cooldown_seconds": max(0, int(round(self._cooldown_until - now_ts))),
            "consecutive_losses": self._consecutive_losses,
            "analysis_only": cooldown_active,
            "reentry_mode": "SMART_REENTRY" if not cooldown_active else "COOLDOWN",
            "last_exit_time": self._last_exit_time,
            "last_exit_price": self._last_exit_price,
            "last_exit_direction": self._last_exit_direction,
            "last_profit_amount": self._last_profit_amount,
            "last_reentry_decision": self._last_reentry_decision,
        }
