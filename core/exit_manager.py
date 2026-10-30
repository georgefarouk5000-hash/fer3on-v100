# =============================================================================
# FER3ON — PHASE 3 | EXIT MANAGER (Demo)
# =============================================================================
# Four independent exit mechanisms, computed from position state + candles:
#   1. INDEPENDENT TP LADDER — TP levels from their own RR ladder
#      (TP_LADDER_RR × SL distance), NOT re-derived from how SL was built.
#   2. PARTIAL EXITS — close TP_LADDER_FRACTIONS of the position per level.
#   3. TRAILING — after TP1: SL → breakeven + BREAKEVEN_BUFFER_ATR × ATR.
#      After TP2: trail at TRAILING_ATR_MULT × ATR behind price.
#   4. TIME EXIT — if neither TP1 nor SL within TIME_EXIT_BARS bars → close.
#
# Advisory by default (PHASE3_EXIT_MANAGER_LIVE_ENABLED = False): actions are
# computed + logged, real positions untouched.
#
# SAFETY CONTRACT: never raises; imports no execution code (no MT5 /
# trade_executor); callers pass plain dicts, get plain dicts back.
# =============================================================================
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_EXIT_RESOLVER_LAST_SIGNATURE: Optional[tuple[str, int, int]] = None
_EXIT_RESOLVER_LAST_RUN = 0.0
_EXIT_RESOLVER_RETRY_SECONDS = 60.0


def _cfg(name: str, default: Any) -> Any:
    try:
        import core.settings as _s
        return getattr(_s, name, default)
    except Exception:
        return default


def _enabled() -> bool:
    return bool(_cfg("PHASE3_EXIT_MANAGER_ENABLED", True))


def _live() -> bool:
    return bool(_cfg("PHASE3_EXIT_MANAGER_LIVE_ENABLED", False))


def _log_path() -> str:
    return str(_cfg("PHASE3_EXIT_MANAGER_LOG_PATH",
                    "data/analytics/exit_manager/exit_actions.jsonl"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1+2. Independent TP ladder with partial-close fractions
# ---------------------------------------------------------------------------

def compute_tp_ladder(
    direction: Optional[str],
    entry_price: Optional[float],
    sl_dist: Optional[float],
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Independent TP levels: entry ± rr × sl_dist, each with its partial
    close fraction. NEVER raises; returns [] on bad input."""
    try:
        from execution.multi_tp import compute_tp_prices

        result = compute_tp_prices(
            entry_price=float(entry_price or 0),
            sl_distance=float(sl_dist or 0),
            direction=str(direction or "").upper(),
            strategy=str(strategy or "SMC").upper(),
        )
        if not result.get("enabled"):
            return []
        return [
            {
                "tier": index + 1,
                "rr": float(level.get("rr", 0) or 0),
                "fraction": float(level.get("close_pct", 0) or 0),
                "price": float(level.get("price", 0) or 0),
                "dist": round(abs(float(level["price"]) - float(entry_price)), 2),
            }
            for index, level in enumerate(result.get("levels", []))
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 3+4. Position-state evaluation: breakeven / trailing / time exit
# ---------------------------------------------------------------------------

def _candle_time(c: Dict[str, Any]) -> str:
    return str(c.get("time") or c.get("timestamp") or "")


def evaluate_exit(
    position: Optional[Dict[str, Any]],
    candles: Optional[List[Dict[str, Any]]],
    atr: Optional[float] = None,
) -> Dict[str, Any]:
    """Evaluate one open position against candles (ascending, with
    time/high/low). `position` keys: direction, entry_price, sl_dist,
    open_time (ISO). Returns an action dict:

        action: NONE | PARTIAL_CLOSE | MOVE_SL_BREAKEVEN | TRAIL |
                TIME_EXIT | CLOSE_ALL | SL_HIT
        plus context fields (tier, new_sl_dist, trail_dist, bars_open...)

    NEVER raises; imports nothing executable.
    """
    out: Dict[str, Any] = {"action": "NONE", "live": _live()}
    try:
        pos = position or {}
        d = str(pos.get("direction") or "").upper()
        entry = float(pos.get("entry_price") or 0)
        sl = float(pos.get("sl_dist") or 0)
        open_t = str(pos.get("open_time") or "")
        if d not in ("BUY", "SELL") or entry <= 0 or sl <= 0:
            out["action"] = "INVALID"
            return out

        ladder = compute_tp_ladder(d, entry, sl, pos.get("strategy"))
        if not ladder:
            out["action"] = "INVALID"
            return out
        tp1, tp2, tp_last = ladder[0], (ladder[1] if len(ladder) > 1 else None), ladder[-1]
        loss_level = (entry - sl) if d == "BUY" else (entry + sl)
        atr_v = max(0.0, float(atr or 0))
        time_exit_bars = int(_cfg("TIME_EXIT_BARS", 24))

        bars = candles or []
        start = 0
        if open_t:
            start = next((i for i, c in enumerate(bars) if _candle_time(c) and _candle_time(c) > open_t),
                         len(bars))
        post = bars[start:]
        out["bars_open"] = len(post)

        highest = entry
        lowest = entry
        for c in post:
            high = float(c.get("high"))
            low = float(c.get("low"))
            highest, lowest = max(highest, high), min(lowest, low)

            # SL first — conservative ordering
            sl_hit = (low <= loss_level) if d == "BUY" else (high >= loss_level)
            if sl_hit:
                out.update(action="SL_HIT", level=round(loss_level, 5))
                return out

            def _touched(level_price: float) -> bool:
                return (high >= level_price) if d == "BUY" else (low <= level_price)

            if _touched(tp_last["price"]):
                out.update(action="CLOSE_ALL", tier=tp_last["tier"], price=tp_last["price"])
                return out
            if tp2 and _touched(tp2["price"]):
                trail = round(float(_cfg("TRAILING_ATR_MULT", 1.0)) * atr_v, 2) if atr_v > 0 else None
                out.update(action="TRAIL", tier=tp2["tier"], fraction=tp2["fraction"],
                           trail_dist=trail, price=tp2["price"])
                return out
            if _touched(tp1["price"]):
                buf = round(float(_cfg("BREAKEVEN_BUFFER_ATR", 0.1)) * atr_v, 2) if atr_v > 0 else 0.0
                new_sl = entry + buf if d == "BUY" else entry - buf
                out.update(action="MOVE_SL_BREAKEVEN", tier=tp1["tier"],
                           fraction=tp1["fraction"], breakeven_buffer=buf,
                           new_sl=round(new_sl, 5), price=tp1["price"])
                return out

        # Time exit: stale trade, no TP1 and no SL within the window
        if len(post) >= time_exit_bars:
            out.update(action="TIME_EXIT", bars_open=len(post),
                       limit=time_exit_bars)
            return out

        return out
    except Exception:
        return {"action": "ERROR", "live": _live()}


def simulate_exit_outcome(
    position: Optional[Dict[str, Any]],
    candles: Optional[List[Dict[str, Any]]],
    atr: Optional[float] = None,
) -> Dict[str, Any]:
    """Replay the advisory TP/SL ladder with worst-case intrabar ordering."""
    out: Dict[str, Any] = {"resolved": False, "outcome": "PENDING"}
    try:
        pos = position or {}
        direction = str(pos.get("direction") or "").upper()
        entry = float(pos.get("entry_price") or 0)
        sl_dist = float(pos.get("sl_dist") or 0)
        open_time = str(pos.get("open_time") or "")
        atr_value = float(atr or 0)
        if (
            direction not in {"BUY", "SELL"}
            or entry <= 0
            or sl_dist <= 0
            or atr_value <= 0
            or not candles
        ):
            return {**out, "reason": "INVALID_OR_INCOMPLETE_POSITION"}

        ladder = compute_tp_ladder(
            direction, entry, sl_dist, str(pos.get("strategy") or "SMC")
        )
        if not ladder:
            return {**out, "reason": "TP_LADDER_UNAVAILABLE"}
        start = next(
            (
                index for index, candle in enumerate(candles)
                if _candle_time(candle) and _candle_time(candle) > open_time
            ),
            len(candles),
        )
        if start >= len(candles):
            return {**out, "reason": "NO_POST_ENTRY_CANDLES"}

        stop = entry - sl_dist if direction == "BUY" else entry + sl_dist
        remaining = 1.0
        realized_r = 0.0
        highest = entry
        lowest = entry
        next_target = 0
        trailing = False
        max_bars = max(
            1,
            int(_cfg("TIME_EXIT_BARS", 24)),
        )
        time_limit = max_bars
        breakeven_buffer = max(
            0.0, float(_cfg("BREAKEVEN_BUFFER_ATR", 0.1)) * atr_value
        )
        trail_distance = max(
            0.0, float(_cfg("TRAILING_ATR_MULT", 1.0)) * atr_value
        )

        def result(outcome: str, index: int, exit_price: float, reason: str) -> Dict[str, Any]:
            return {
                "resolved": True,
                "outcome": outcome,
                "outcome_bar": index - start + 1,
                "exit_price": round(exit_price, 5),
                "simulated_r": round(realized_r, 5),
                "exit_reason": reason,
            }

        def signed_r(price: float) -> float:
            movement = price - entry if direction == "BUY" else entry - price
            return movement / sl_dist

        for index in range(start, len(candles)):
            candle = candles[index]
            try:
                high = float(candle["high"])
                low = float(candle["low"])
            except (KeyError, TypeError, ValueError):
                continue
            bars_open = index - start + 1
            stop_hit = low <= stop if direction == "BUY" else high >= stop
            remaining_targets = ladder[next_target:]
            touched_targets = [
                target for target in remaining_targets
                if (
                    high >= float(target.get("price") or 0)
                    if direction == "BUY"
                    else low <= float(target.get("price") or 0)
                )
            ]
            pending_target = (
                ladder[next_target] if next_target < len(ladder) else None
            )
            target_hit = (
                pending_target is not None
                and pending_target in touched_targets
            )
            if stop_hit and touched_targets:
                realized_r += remaining * signed_r(stop)
                return result("LOSS_INTRABAR_AMBIGUOUS", index, stop, "SL_AND_TP_SAME_BAR")
            if stop_hit:
                realized_r += remaining * signed_r(stop)
                outcome = (
                    "WIN" if realized_r > 1e-8
                    else "LOSS" if realized_r < -1e-8
                    else "BREAKEVEN"
                )
                return result(outcome, index, stop, "STOP")
            if target_hit and pending_target is not None:
                target_price = float(pending_target["price"])
                if next_target == len(ladder) - 1:
                    close_fraction = remaining
                else:
                    close_fraction = float(pending_target.get("fraction") or 0)
                    if close_fraction > 1:
                        close_fraction /= 100.0
                    close_fraction = min(remaining, max(0.0, close_fraction))
                realized_r += close_fraction * signed_r(target_price)
                remaining -= close_fraction
                next_target += 1
                if pending_target.get("tier", next_target) == 1:
                    stop = (
                        entry + breakeven_buffer
                        if direction == "BUY"
                        else entry - breakeven_buffer
                    )
                if next_target >= 2:
                    trailing = True
                if remaining <= 1e-8:
                    return result("WIN", index, target_price, "TP_LADDER")

            highest = max(highest, high)
            lowest = min(lowest, low)
            if trailing and trail_distance > 0:
                if direction == "BUY":
                    stop = max(stop, highest - trail_distance)
                else:
                    stop = min(stop, lowest + trail_distance)

            if bars_open >= time_limit and next_target == 0:
                try:
                    exit_price = float(candle.get("close") or 0)
                except (TypeError, ValueError):
                    exit_price = 0.0
                if exit_price <= 0:
                    exit_price = (high + low) / 2.0
                realized_r += remaining * signed_r(exit_price)
                return result("TIMEOUT", index, exit_price, "TIME_EXIT")
            if bars_open >= 48:
                try:
                    exit_price = float(candle.get("close") or 0)
                except (TypeError, ValueError):
                    exit_price = 0.0
                if exit_price <= 0:
                    exit_price = (high + low) / 2.0
                realized_r += remaining * signed_r(exit_price)
                return result("TIMEOUT", index, exit_price, "RESEARCH_HORIZON")
        return {**out, "reason": "INSUFFICIENT_POST_ENTRY_BARS"}
    except Exception as exc:
        return {**out, "reason": f"{type(exc).__name__}: {exc}"}


def resolve_exit_outcomes(
    candles: Optional[List[Dict[str, Any]]],
    *,
    log_path: Optional[str] = None,
    event_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist one simulated exit outcome for each cost-audited closed trade."""
    global _EXIT_RESOLVER_LAST_SIGNATURE, _EXIT_RESOLVER_LAST_RUN
    try:
        if not _enabled():
            return {"ok": False, "resolved": 0, "reason": "disabled"}
        from core.trade_event_ledger import TRADE_EVENTS_FILE
        destination = log_path or _log_path()
        source = event_path or TRADE_EVENTS_FILE
        if not candles or not os.path.exists(source):
            return {"ok": False, "resolved": 0, "reason": "no candles or event ledger"}
        source_stat = os.stat(source)
        signature = (
            os.path.abspath(source),
            int(source_stat.st_size),
            int(source_stat.st_mtime_ns),
        )
        now = time.monotonic()
        if (
            signature == _EXIT_RESOLVER_LAST_SIGNATURE
            and now - _EXIT_RESOLVER_LAST_RUN < _EXIT_RESOLVER_RETRY_SECONDS
        ):
            return {"ok": True, "resolved": 0, "reason": "retry deferred"}
        with open(source, "r", encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        decisions = {
            str(event.get("correlation_id")): event
            for event in events
            if event.get("event_type") == "DECISION" and event.get("correlation_id")
        }
        closed_ids = {
            str(event.get("correlation_id"))
            for event in events
            if event.get("event_type") == "TRADE_CLOSED"
            and event.get("correlation_id")
        }
        existing_ids = set()
        if os.path.exists(destination):
            with open(destination, "r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if row.get("record_type") == "EXIT_SIMULATION_OUTCOME":
                        existing_ids.add(str(row.get("decision_id") or ""))

        resolved = 0
        for decision_id in closed_ids:
            decision = decisions.get(decision_id)
            if decision is None or decision_id in existing_ids:
                continue
            entry = float(decision.get("entry_price") or 0)
            stop = float(decision.get("stop_loss") or 0)
            sl_dist = abs(entry - stop)
            simulated = simulate_exit_outcome(
                {
                    "direction": decision.get("signal"),
                    "entry_price": entry,
                    "sl_dist": sl_dist,
                    "open_time": decision.get("timestamp"),
                    "strategy": decision.get("strategy"),
                },
                candles,
                atr=float(decision.get("atr") or 0),
            )
            if not simulated.get("resolved"):
                continue
            close_event = next(
                (
                    event for event in events
                    if event.get("event_type") == "TRADE_CLOSED"
                    and str(event.get("correlation_id")) == decision_id
                    and event.get("entry_cost_complete") is True
                ),
                None,
            )
            record = {
                "record_type": "EXIT_SIMULATION_OUTCOME",
                "decision_id": decision_id,
                "candidate_id": decision.get("candidate_id"),
                "ticket": close_event.get("position_id") if close_event else None,
                "symbol": decision.get("symbol"),
                "strategy": decision.get("strategy"),
                "direction": decision.get("signal"),
                "outcome": simulated["outcome"],
                "outcome_bar": simulated.get("outcome_bar"),
                "simulated_r": simulated.get("simulated_r"),
                "simulated_exit_price": simulated.get("exit_price"),
                "exit_reason": simulated.get("exit_reason"),
                "simulation_model": "ENTRY_ATR_FIXED_CONSERVATIVE_OHLC",
                "actual_profit": (
                    close_event.get("total_position_net_profit")
                    if close_event else None
                ),
                "actual_outcome": (
                    "WIN" if float(close_event.get("total_position_net_profit") or 0) > 0
                    else "LOSS" if float(close_event.get("total_position_net_profit") or 0) < 0
                    else "BREAKEVEN"
                ) if close_event else None,
                "actual_costs_complete": close_event is not None,
                "logged_at": _utc_now_iso(),
            }
            if log_exit_action(record, log_path=destination):
                existing_ids.add(decision_id)
                resolved += 1
        _EXIT_RESOLVER_LAST_SIGNATURE = signature
        _EXIT_RESOLVER_LAST_RUN = now
        return {"ok": True, "resolved": resolved, "closed_trades": len(closed_ids)}
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"ok": False, "resolved": 0, "reason": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Ledger (advisory logging)
# ---------------------------------------------------------------------------

def log_exit_action(record: Optional[Dict[str, Any]], *, log_path: Optional[str] = None) -> bool:
    try:
        if not _enabled():
            return False
        rec = dict(record or {})
        rec.setdefault("record_type", "EXIT_ACTION")
        rec.setdefault("logged_at", _utc_now_iso())
        path = log_path or _log_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False
