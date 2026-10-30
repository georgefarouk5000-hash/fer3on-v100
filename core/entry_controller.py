# =============================================================================
# FER3ON — PHASE 2 | ENTRY CONTROLLER + STRUCTURAL SL (Demo)
# =============================================================================
# Replaces "enter at market the instant a signal fires" with:
#   1. A pullback LIMIT entry plan (retracement of PULLBACK_DEPTH_ATR × ATR),
#      valid for ENTRY_TTL_BARS bars, then expired.
#   2. A STRUCTURE-anchored SL: beyond the opposing swing ± ATR buffer,
#      hard-capped at the shared STRUCTURAL_SL_CAP_DOLLARS limit.
#
# MODE: advisory by default (PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED = False):
# plans are computed + logged, live orders untouched. Flipping the live flag
# on Demo makes these the values handed to the finalizer.
#
# SAFETY CONTRACT (same as analytics/shadow_counterfactual.py):
#   - Never raises. Never imports execution code (no MT5 / trade_executor).
#   - Nothing here is read back into a live decision unless the LIVE flag
#     is on AND the caller explicitly consumes the returned plan.
# =============================================================================
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Config access (defensive)
# ---------------------------------------------------------------------------

def _cfg(name: str, default: Any) -> Any:
    try:
        import core.settings as _s
        return getattr(_s, name, default)
    except Exception:
        return default


def _enabled() -> bool:
    return bool(_cfg("PHASE2_ENTRY_CONTROLLER_ENABLED", True))


def _live() -> bool:
    return bool(_cfg("PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED", False))


def _log_path() -> str:
    return str(_cfg("PHASE2_ENTRY_CONTROLLER_LOG_PATH",
                    "data/analytics/entry_controller/entry_plans.jsonl"))


def _quarantine_path() -> str:
    return str(_cfg("PHASE2_ENTRY_CONTROLLER_QUARANTINE_PATH",
                    "data/analytics/quarantine/entry_plans_invalid.jsonl"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Structural SL
# ---------------------------------------------------------------------------

def _swing_level(
    structure_analysis: Optional[Dict[str, Any]],
    direction: str,
    entry_price: Optional[float] = None,
) -> Optional[float]:
    """Return the nearest confirmed protective pivot on the valid side."""
    try:
        sa = structure_analysis or {}
        seq_key = "swing_lows" if direction == "BUY" else "swing_highs"
        alt_key = "lows" if direction == "BUY" else "highs"
        seq = sa.get(seq_key) or sa.get(alt_key) or []
        levels = []
        if seq:
            for lvl in seq:
                value = lvl.get("price") if isinstance(lvl, dict) else lvl
                if value is None:
                    continue
                try:
                    level = float(value)
                except (TypeError, ValueError):
                    continue
                if level > 0:
                    levels.append(level)
        single_key = "last_swing_low" if direction == "BUY" else "last_swing_high"
        v = sa.get(single_key)
        if v is None:
            v = sa.get("swing_low" if direction == "BUY" else "swing_high")
        if v is not None:
            try:
                level = float(v)
            except (TypeError, ValueError):
                level = 0.0
            if level > 0:
                levels.append(level)
        levels = list(dict.fromkeys(levels))
        try:
            entry = float(entry_price) if entry_price is not None else 0.0
        except (TypeError, ValueError):
            entry = 0.0
        if entry > 0:
            eligible = [
                level for level in levels
                if (level < entry if direction == "BUY" else level > entry)
            ]
            if not eligible:
                return None
            return max(eligible) if direction == "BUY" else min(eligible)
        return levels[-1] if levels else None
    except Exception:
        return None


def compute_structural_sl_dist(
    direction: Optional[str],
    entry_price: Optional[float],
    atr: Optional[float],
    structure_analysis: Optional[Dict[str, Any]] = None,
    strategy: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """SL distance anchored beyond the opposing swing, hard-capped.
    Returns a dict or None. NEVER raises."""
    try:
        d = str(direction or "").upper()
        entry = float(entry_price or 0)
        atr_v = max(0.0, float(atr or 0))
        if entry <= 0 or d not in ("BUY", "SELL"):
            return None

        cap = float(_cfg("STRUCTURAL_SL_CAP_DOLLARS", 15.0))
        buf = float(_cfg("STRUCTURAL_SL_ATR_BUFFER", 0.3)) * atr_v

        raw_level = _swing_level(structure_analysis, d)
        lvl = _swing_level(structure_analysis, d, entry)
        if lvl is None:
            if raw_level is not None:
                return {"sl_dist": None, "source": "structure_invalid", "cap": cap,
                        "reason": "swing_level_on_wrong_side_of_entry"}
            if atr_v <= 0:
                return None
            dist = 1.5 * atr_v
            return {"sl_dist": round(min(dist, cap), 2), "source": "atr_fallback",
                    "cap": cap, "capped": dist > cap}

        sl_price = (lvl - buf) if d == "BUY" else (lvl + buf)
        dist = (entry - sl_price) if d == "BUY" else (sl_price - entry)
        if dist <= 0:
            return {"sl_dist": None, "source": "structure_invalid", "cap": cap,
                    "reason": "swing_level_on_wrong_side_of_entry"}

        return {"sl_dist": round(min(dist, cap), 2), "source": "structure",
                "cap": cap, "uncapped_dist": round(dist, 2), "capped": dist > cap,
                "swing_level": round(lvl, 5), "buffer": round(buf, 5)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Entry plan
# ---------------------------------------------------------------------------

def plan_entry(
    *,
    signal_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    decision_bar_time: Optional[Any] = None,
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    signal_price: Optional[float] = None,
    atr: Optional[float] = None,
    baseline_sl_dist: Optional[float] = None,
    baseline_tp_dist: Optional[float] = None,
    structure_analysis: Optional[Dict[str, Any]] = None,
    strategy: Optional[str] = None,
    confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the entry plan. Advisory unless LIVE flag is on. NEVER raises."""
    plan: Dict[str, Any] = {
        "record_type": "ENTRY_PLAN",
        "signal_id": signal_id,
        "candidate_id": candidate_id or signal_id,
        "decision_bar_time": decision_bar_time,
        "symbol": symbol,
        "direction": str(direction or "").upper() or None,
        "signal_time": _utc_now_iso(),
        "live": _live(),
        "entry_mode": "SKIP",
        "status": "INVALID",
        "entry_outcome": "PENDING",
        "baseline_outcome": "PENDING",
        "outcome_horizon_bars": 48,
    }
    try:
        d = plan["direction"]
        price = float(signal_price or 0)
        atr_v = max(0.0, float(atr or 0))
        if d not in ("BUY", "SELL") or price <= 0:
            return plan

        depth = float(_cfg("PULLBACK_DEPTH_ATR", 0.5)) * atr_v
        if atr_v > 0 and depth > 0:
            limit_price = (price - depth) if d == "BUY" else (price + depth)
            plan.update(entry_mode="LIMIT_PULLBACK",
                        limit_price=round(limit_price, 5),
                        pullback_depth=round(depth, 5),
                        ttl_bars=int(_cfg("ENTRY_TTL_BARS", 6)))
        else:
            plan.update(entry_mode="MARKET", limit_price=round(price, 5),
                        pullback_depth=0.0, ttl_bars=0)

        planned_entry = float(plan.get("limit_price") or 0.0)
        if planned_entry <= 0:
            plan["status"] = "INVALID"
            return plan
        sl = compute_structural_sl_dist(
            d, planned_entry, atr_v, structure_analysis, strategy
        )
        if sl and sl.get("sl_dist"):
            plan["structural_sl"] = sl
            sl_distance = float(sl["sl_dist"])
            if d == "BUY":
                plan["cancel_level"] = round(planned_entry - sl_distance, 5)
            else:
                plan["cancel_level"] = round(planned_entry + sl_distance, 5)
            fallback_rr = 1.2
            try:
                from core.settings import MULTI_TP_PROFILE
                rr_value = MULTI_TP_PROFILE.get(
                    str(strategy or "").upper(), {}
                ).get("tp1_rr", fallback_rr)
                rr = float(rr_value if rr_value is not None else fallback_rr)
            except (TypeError, ValueError):
                rr = fallback_rr
            tp_distance = sl_distance * rr
            plan["expected_sl"] = round(plan["cancel_level"], 5)
            plan["expected_tp"] = round(
                planned_entry + tp_distance if d == "BUY"
                else planned_entry - tp_distance,
                5,
            )
        else:
            plan["structural_sl"] = sl or {"sl_dist": None, "source": "unavailable"}
            plan["cancel_level"] = None
            plan["expected_sl"] = None
            plan["expected_tp"] = None

        plan["confidence"] = confidence
        plan["strategy"] = strategy
        try:
            baseline_sl = float(baseline_sl_dist or 0)
            baseline_tp = float(baseline_tp_dist or 0)
        except (TypeError, ValueError):
            baseline_sl = baseline_tp = 0.0
        if baseline_sl > 0 and baseline_tp > 0:
            plan["baseline_entry_price"] = round(price, 5)
            plan["baseline_sl_dist"] = baseline_sl
            plan["baseline_tp_dist"] = baseline_tp
        plan["opportunity_mode"] = "PREPARE_THEN_CONFIRM"
        plan["confirmation_conditions"] = {
            "direction": d,
            "minimum_confidence": 0.60,
            "structure_valid": bool(
                plan["structural_sl"].get("source") == "structure"
            ),
            "entry_touched": plan["entry_mode"] == "MARKET",
            "cancel_if_price_crosses": plan["cancel_level"],
            "cancel_after_bars": int(plan.get("ttl_bars") or 0),
        }
        plan["status"] = "PENDING" if plan["entry_mode"] == "LIMIT_PULLBACK" else "READY"
        return plan
    except Exception:
        plan["status"] = "ERROR"
        return plan


def scan_opportunity_zones(
    *,
    symbol: Optional[str] = None,
    rates: Optional[Any] = None,
    atr: Optional[float] = None,
    structure_analysis: Optional[Dict[str, Any]] = None,
    strategy: Optional[str] = None,
    max_candidates: int = 2,
) -> List[Dict[str, Any]]:
    """Prepare candidate zones before a final entry signal is consumed.

    This is advisory only: it creates plans and never places or modifies an
    order. Candidates require a recent structural level and valid OHLC data.
    """
    try:
        from core.main_helpers import rates_to_candles
        candles = rates_to_candles(rates)
        if not candles or not structure_analysis:
            return []
        current_price = float(candles[-1].get("close") or 0)
        if current_price <= 0 or float(atr or 0) <= 0:
            return []
        analysis = structure_analysis
        directions = []
        bias = str(analysis.get("structure_bias") or "").upper()
        if bias in {"BUY", "SELL"}:
            directions.append(bias)
        else:
            directions.extend(("BUY", "SELL"))
        plans: List[Dict[str, Any]] = []
        decision_bar_time = _candle_time(candles[-1])
        if not decision_bar_time:
            return []
        for direction in directions[:max(1, int(max_candidates))]:
            level_key = "swing_lows" if direction == "BUY" else "swing_highs"
            if not (analysis.get(level_key) or analysis.get(
                "lows" if direction == "BUY" else "highs"
            )):
                continue
            plan = plan_entry(
                signal_id=f"zone-{symbol}-{strategy}-{direction}-{decision_bar_time}",
                candidate_id=f"zone-{symbol}-{strategy}-{direction}-{decision_bar_time}",
                decision_bar_time=decision_bar_time,
                symbol=symbol,
                direction=direction,
                signal_price=current_price,
                atr=atr,
                structure_analysis=analysis,
                strategy=strategy,
            )
            plan["record_type"] = "OPPORTUNITY_ZONE"
            plan["opportunity_source"] = "PROACTIVE_STRUCTURE_SCAN"
            plans.append(plan)
        return plans
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Ledger: log plans, resolve LIMIT fill/expiry against real candles
# ---------------------------------------------------------------------------

def log_entry_plan(plan: Optional[Dict[str, Any]], *, log_path: Optional[str] = None) -> bool:
    try:
        if not _enabled():
            return False
        rec = dict(plan or {})
        from core.data_quality import quarantine, stamp
        if str(rec.get("direction") or "").upper() not in {"BUY", "SELL"} or float(rec.get("limit_price") or 0) <= 0:
            quarantine(rec, "INVALID_ENTRY_PLAN", _quarantine_path())
            return False
        rec.setdefault("entry_outcome", "PENDING")
        rec.setdefault("baseline_outcome", "PENDING")
        rec.setdefault("outcome_horizon_bars", 48)
        stamp(rec)
        rec.setdefault("logged_at", _utc_now_iso())
        path = log_path or _log_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        rec.setdefault("candidate_id", rec.get("signal_id"))
        from core.trade_event_ledger import append_candidate_record
        return append_candidate_record(path, rec)
    except Exception:
        return False


def _candle_time(c: Dict[str, Any]) -> str:
    return str(c.get("time") or c.get("timestamp") or "")


def _simulate_fixed_levels(
    *,
    direction: str,
    sl_level: float,
    tp_level: float,
    candles: List[Dict[str, Any]],
    start: int,
    horizon: int,
    filled_on_start_bar: bool = False,
) -> Optional[tuple[str, int]]:
    end = min(start + horizon, len(candles))
    for index in range(start, end):
        candle = candles[index]
        try:
            high, low = float(candle["high"]), float(candle["low"])
        except (KeyError, TypeError, ValueError):
            continue
        hit_sl = low <= sl_level if direction == "BUY" else high >= sl_level
        hit_tp = high >= tp_level if direction == "BUY" else low <= tp_level
        bars = index - start + 1
        if hit_sl and hit_tp:
            return "LOSS_INTRABAR_AMBIGUOUS", bars
        if hit_sl:
            return "LOSS", bars
        if hit_tp:
            if filled_on_start_bar and index == start:
                return "LOSS_INTRABAR_AMBIGUOUS", bars
            return "WIN", bars
    if len(candles) - start >= horizon:
        return "TIMEOUT", horizon
    return None


def resolve_entry_plans(candles: Optional[List[Dict[str, Any]]], *,
                        log_path: Optional[str] = None) -> Dict[str, Any]:
    """Resolve pullback fills and matched hypothetical outcomes from candles."""
    try:
        path = log_path or _log_path()
        if not candles or not os.path.exists(path):
            return {"ok": False, "resolved": 0, "reason": "no candles or no ledger"}

        with open(path, "r", encoding="utf-8") as fh:
            records = [json.loads(l) for l in fh if l.strip()]

        resolved = 0
        outcomes_resolved = 0
        for rec in records:
            if rec.get("status") not in {"PENDING", "READY", "FILLED"}:
                continue
            try:
                d = str(rec.get("direction") or "").upper()
                sig_t = str(rec.get("signal_time") or "")
                if d not in {"BUY", "SELL"} or not sig_t:
                    continue
                start = None
                for i, c in enumerate(candles):
                    if _candle_time(c) and _candle_time(c) > sig_t:
                        start = i
                        break
                if start is None:
                    continue
                if rec.get("status") == "READY" and rec.get("entry_mode") == "MARKET":
                    rec["status"] = "FILLED"
                    rec["filled_bar"] = 1
                    rec["filled_time"] = _candle_time(candles[start])
                    rec["filled_price"] = float(rec.get("limit_price") or 0)
                    resolved += 1
                elif rec.get("status") == "PENDING" and rec.get("entry_mode") == "LIMIT_PULLBACK":
                    limit = float(rec.get("limit_price") or 0)
                    ttl = max(1, int(rec.get("ttl_bars") or 1))
                    if limit <= 0:
                        continue
                    touched_index = None
                    for j in range(start, min(start + ttl, len(candles))):
                        field = "low" if d == "BUY" else "high"
                        value = candles[j].get(field)
                        if value is None:
                            continue
                        price = float(value)
                        if (d == "BUY" and price <= limit) or (
                            d == "SELL" and price >= limit
                        ):
                            touched_index = j
                            break
                    if touched_index is not None:
                        rec["status"] = "FILLED"
                        rec["filled_bar"] = touched_index - start + 1
                        rec["filled_time"] = _candle_time(candles[touched_index])
                        rec["filled_price"] = limit
                        resolved += 1
                    elif len(candles) - start >= ttl:
                        rec["status"] = "EXPIRED"
                        rec["entry_outcome"] = "NOT_FILLED"
                        resolved += 1

                baseline_outcome = rec.get("baseline_outcome")
                if baseline_outcome == "PENDING":
                    try:
                        baseline_entry = float(rec.get("baseline_entry_price") or 0)
                        baseline_sl = float(rec.get("baseline_sl_dist") or 0)
                        baseline_tp = float(rec.get("baseline_tp_dist") or 0)
                        if baseline_entry > 0 and baseline_sl > 0 and baseline_tp > 0:
                            sl_level = baseline_entry - baseline_sl if d == "BUY" else baseline_entry + baseline_sl
                            tp_level = baseline_entry + baseline_tp if d == "BUY" else baseline_entry - baseline_tp
                            baseline_result = _simulate_fixed_levels(
                                direction=d,
                                sl_level=sl_level,
                                tp_level=tp_level,
                                candles=candles,
                                start=start,
                                horizon=max(1, int(rec.get("outcome_horizon_bars") or 48)),
                            )
                            if baseline_result is not None:
                                rec["baseline_outcome"], rec["baseline_outcome_bar"] = baseline_result
                                outcomes_resolved += 1
                    except (TypeError, ValueError):
                        pass

                if rec.get("status") == "FILLED" and rec.get("entry_outcome") == "PENDING":
                    fill_time = str(rec.get("filled_time") or "")
                    fill_index = next(
                        (
                            index for index, candle in enumerate(candles)
                            if fill_time and _candle_time(candle) == fill_time
                        ),
                        -1,
                    )
                    planned_entry = float(rec.get("filled_price") or rec.get("limit_price") or 0)
                    sl_level = float(rec.get("expected_sl") or 0)
                    tp_level = float(rec.get("expected_tp") or 0)
                    if fill_index < 0 or planned_entry <= 0 or sl_level <= 0 or tp_level <= 0:
                        continue
                    result = _simulate_fixed_levels(
                        direction=d,
                        sl_level=sl_level,
                        tp_level=tp_level,
                        candles=candles,
                        start=fill_index,
                        horizon=max(1, int(rec.get("outcome_horizon_bars") or 48)),
                        filled_on_start_bar=True,
                    )
                    if result is not None:
                        rec["entry_outcome"], rec["entry_outcome_bar"] = result
                        rec["entry_outcome_resolved_at"] = _utc_now_iso()
                        outcomes_resolved += 1
            except Exception:
                continue

        with open(path, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return {
            "ok": True,
            "resolved": resolved,
            "outcomes_resolved": outcomes_resolved,
            "total": len(records),
        }
    except Exception:
        return {"ok": False, "resolved": 0, "reason": "exception"}


def summary(*, log_path: Optional[str] = None) -> Dict[str, Any]:
    """Fill-rate stats: how often pullback entries actually fill. NEVER raises."""
    try:
        path = log_path or _log_path()
        out: Dict[str, Any] = {"ok": True, "total": 0, "PENDING": 0, "FILLED": 0,
                               "EXPIRED": 0, "READY": 0, "fill_rate": None}
        if not os.path.exists(path):
            return out
        with open(path, "r", encoding="utf-8") as fh:
            records = [json.loads(l) for l in fh if l.strip()]
        out["total"] = len(records)
        for rec in records:
            st = rec.get("status")
            if st in out:
                out[st] += 1
        decided = out["FILLED"] + out["EXPIRED"]
        if decided > 0:
            out["fill_rate"] = round(out["FILLED"] / decided, 4)
        return out
    except Exception:
        return {"ok": False}


def get_entry_plans_summary(*, log_path: Optional[str] = None) -> Dict[str, Any]:
    """Backward-compatible name used by the main heartbeat resolver."""
    return summary(log_path=log_path)
