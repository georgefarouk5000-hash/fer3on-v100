"""Append-only correlation events for decisions, fills, and MT5 closes."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any


TRADE_EVENTS_FILE = "data/history/trade_events.jsonl"
_EVENTS_LOCK = threading.Lock()
_CANDIDATE_LOG_LOCK = threading.Lock()
_KNOWN_CANDIDATE_LOGS: dict[str, set[str]] = {}


def create_trade_correlation_id(
    *,
    symbol: str,
    strategy: str,
    signal: str,
    decision_bar_time: Any,
    entry_price: Any,
    stop_loss: Any,
    take_profit: Any,
) -> str:
    identity = "|".join(
        str(value or "").strip()
        for value in (
            symbol,
            strategy,
            signal,
            decision_bar_time,
            round(float(entry_price or 0.0), 5),
            round(float(stop_loss or 0.0), 5),
            round(float(take_profit or 0.0), 5),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def create_snapshot_correlation_id(
    snapshot: dict[str, Any],
    *,
    symbol: str,
    strategy: str,
) -> str:
    signal = str(snapshot.get("signal") or "").upper()
    try:
        entry = float(snapshot.get("entry_price") or 0.0)
        sl_distance = float(snapshot.get("sl_dist") or 0.0)
        tp_distance = float(snapshot.get("tp_dist") or 0.0)
    except (TypeError, ValueError):
        return ""
    if signal not in {"BUY", "SELL"} or entry <= 0 or sl_distance <= 0 or tp_distance <= 0:
        return ""
    if signal == "BUY":
        stop_loss, take_profit = entry - sl_distance, entry + tp_distance
    else:
        stop_loss, take_profit = entry + sl_distance, entry - tp_distance
    return create_trade_correlation_id(
        symbol=symbol,
        strategy=strategy,
        signal=signal,
        decision_bar_time=snapshot.get("decision_bar_time"),
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def create_signal_id(*parts: Any) -> str:
    identity = "|".join(str(value or "").strip() for value in parts)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def create_candidate_id(
    *,
    symbol: str,
    strategy: str,
    signal: str,
    decision_bar_time: Any,
) -> str:
    """Return one stable ID per signal on a closed decision bar."""
    if decision_bar_time in (None, ""):
        return ""
    direction = str(signal or "").strip().upper()
    if direction not in {"BUY", "SELL"}:
        return ""
    return create_signal_id(
        str(symbol or "").strip().upper(),
        str(strategy or "").strip().upper(),
        direction,
        decision_bar_time,
    )


def build_mt5_trade_comment(strategy: str, correlation_id: str) -> str:
    strategy_code = "D" if str(strategy or "").upper() == "DAILY" else "S"
    return f"F3-{strategy_code}-{str(correlation_id)[:24]}"[:31]


def build_entry_attribution(
    snapshot: dict[str, Any],
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract auditable entry conditions without inferring absent signals."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    strategy = str(snapshot.get("strategy") or "UNKNOWN").upper()
    smc = snapshot.get("smc_details")
    smc = smc if isinstance(smc, dict) else {}
    structure = snapshot.get("structure")
    structure = structure if isinstance(structure, dict) else {}
    structure_analysis = snapshot.get("structure_analysis")
    structure_analysis = (
        structure_analysis if isinstance(structure_analysis, dict) else {}
    )
    candle = snapshot.get("candle")
    candle = candle if isinstance(candle, dict) else {}
    readiness = snapshot.get("entry_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    quality_gate = snapshot.get("quality_gate")
    quality_gate = quality_gate if isinstance(quality_gate, dict) else {}
    confidence = snapshot.get("confidence")
    confidence = confidence if isinstance(confidence, dict) else {}

    condition_map = (
        ("LIQUIDITY_SWEEP", smc.get("sweep")),
        ("BOS", smc.get("bos")),
        ("FVG", smc.get("fvg")),
        ("ORDER_BLOCK", smc.get("ob")),
        ("MITIGATION", smc.get("mitigation")),
        ("BREAKER", smc.get("breaker")),
        ("RETEST", smc.get("retest")),
        ("PREMIUM_DISCOUNT_ALIGNMENT", smc.get("premium_discount_aligned")),
    )
    conditions = [name for name, present in condition_map if bool(present)]

    structure_state = str(structure.get("structure") or "").upper()
    choch_state = str(structure_analysis.get("choch") or "").upper()
    bos_state = str(structure_analysis.get("bos") or "").upper()
    signal = str(snapshot.get("signal") or "").upper()
    if (
        bos_state == "BOS_UP" and signal == "BUY"
        or bos_state == "BOS_DOWN" and signal == "SELL"
    ):
        conditions.append("BOS")
    choch_strength = str(
        structure_analysis.get("choch_strength") or ""
    ).upper()
    if (
        structure_state.startswith("TRANSITION")
        or choch_state.startswith("CHOCH")
        or choch_strength in {"MODERATE", "STRONG"}
        or bool(smc.get("choch"))
    ):
        conditions.append("CHOCH")
    if candle.get("confirmed") is True:
        conditions.append("CANDLE_CONFIRMATION")
    if structure.get("mtf_aligned") is True:
        conditions.append("MTF_ALIGNMENT")
    if strategy == "DAILY":
        readiness_reason = str(readiness.get("reason") or "")
        if readiness_reason:
            conditions.append(readiness_reason.upper())
        else:
            conditions.append("DAILY_SETUP")

    conditions = list(dict.fromkeys(conditions))
    reason = (
        f"{strategy}: {' + '.join(conditions)}"
        if conditions
        else f"{strategy}: {str(snapshot.get('entry_grade') or 'STRATEGY_SIGNAL')}"
    )
    decision_reasons = decision.get("reasons")
    if not isinstance(decision_reasons, (list, tuple)):
        decision_reasons = []

    evidence = {
        "smc": smc,
        "structure": {
            key: structure.get(key)
            for key in ("structure", "bias", "mtf_aligned", "h1", "h4")
            if key in structure
        },
        "structure_analysis": {
            key: structure_analysis.get(key)
            for key in (
                "structure_bias",
                "structure_strength",
                "choch_strength",
            )
            if key in structure_analysis
        },
        "candle": candle,
        "entry_readiness": readiness,
        "entry_grade": snapshot.get("entry_grade"),
        "quality_gate_mode": quality_gate.get("mode"),
        "quality_score": snapshot.get("quality_score"),
        "confidence_pct": confidence.get("pct"),
        "authority": {
            "mode": decision.get("mode"),
            "verdict": decision.get("verdict"),
            "reason": decision.get("reason"),
            "hard_block_reason": decision.get("hard_block_reason"),
            "reasons": list(decision_reasons),
        },
    }
    return {
        "entry_reason": reason,
        "entry_conditions": conditions,
        "entry_evidence": evidence,
    }


def append_trade_event(
    event_type: str,
    correlation_id: str,
    **details: Any,
) -> dict[str, Any]:
    if not event_type or not correlation_id:
        raise ValueError("event_type and correlation_id are required")

    record = {
        "event_type": str(event_type),
        "correlation_id": str(correlation_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    encoded = json.dumps(record, ensure_ascii=False, default=str)
    parent = os.path.dirname(TRADE_EVENTS_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _EVENTS_LOCK:
        with open(TRADE_EVENTS_FILE, "a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return record


def append_candidate_record(path: str, record: dict[str, Any]) -> bool:
    """Append one candidate log row, idempotently per stable candidate ID."""
    candidate_id = str(record.get("candidate_id") or "")
    target = os.path.abspath(path)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _CANDIDATE_LOG_LOCK:
        if candidate_id:
            known = _KNOWN_CANDIDATE_LOGS.get(target)
            if known is None:
                known = set()
                if os.path.exists(target):
                    with open(target, "r", encoding="utf-8") as existing:
                        for line in existing:
                            try:
                                prior = json.loads(line)
                            except (TypeError, ValueError):
                                continue
                            if isinstance(prior, dict) and prior.get("candidate_id"):
                                known.add(str(prior["candidate_id"]))
                _KNOWN_CANDIDATE_LOGS[target] = known
            if candidate_id in known:
                return True
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if candidate_id:
            _KNOWN_CANDIDATE_LOGS[target].add(candidate_id)
    return True
