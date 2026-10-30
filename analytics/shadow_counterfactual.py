# =============================================================================
# FER3ON — PHASE 1 | SHADOW COUNTERFACTUAL LEDGER (REJECTED_SHADOW)
# =============================================================================
# Purpose: every signal the live pipeline REJECTS (quality gate, hard gate,
# authority, portfolio veto, ...) is recorded here as REJECTED_SHADOW, then
# its hypothetical outcome (WIN / LOSS / TIMEOUT) is resolved later against
# real candles. This answers the question the current system cannot answer:
# "are we rejecting good trades?" — with data, not opinion.
#
# SAFETY CONTRACT (mirrors brain/faie/shadow_logging.py):
#   - LOGGING ONLY. Nothing here is ever read back into the real decision
#     path. No function in this module may change, delay, or block a real
#     decision.
#   - Every public function must NEVER raise. All failure modes (bad record,
#     disk full, missing settings, ...) are swallowed and reported through
#     return values only.
#   - This module imports NO execution code: no MetaTrader5, no
#     core.trade_executor, no order-sending path of any kind.
# =============================================================================
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


_LEDGER_LOCK = threading.RLock()
_KNOWN_REJECTIONS: Dict[str, set[str]] = {}


# ---------------------------------------------------------------------------
# Config access (defensive — a missing setting must never break logging)
# ---------------------------------------------------------------------------

def _default_log_path() -> str:
    try:
        from core.settings import SHADOW_COUNTERFACTUAL_LOG_PATH
        return SHADOW_COUNTERFACTUAL_LOG_PATH
    except Exception:
        return "data/analytics/shadow_counterfactual/rejected_shadow_2026-09-01-clean.jsonl"


def _enabled() -> bool:
    try:
        from core.settings import SHADOW_COUNTERFACTUAL_ENABLED
        return bool(SHADOW_COUNTERFACTUAL_ENABLED)
    except Exception:
        return True


def _horizon() -> int:
    try:
        from core.settings import SHADOW_COUNTERFACTUAL_HORIZON_BARS
        return max(1, int(SHADOW_COUNTERFACTUAL_HORIZON_BARS))
    except Exception:
        return 48


def _min_samples() -> int:
    try:
        from core.settings import SHADOW_COUNTERFACTUAL_MIN_SAMPLES
        return max(1, int(SHADOW_COUNTERFACTUAL_MIN_SAMPLES))
    except Exception:
        return 100


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# WRITE — log one rejected signal
# ---------------------------------------------------------------------------

def log_rejected_shadow(record: Optional[Dict[str, Any]], *, log_path: Optional[str] = None) -> bool:
    """Append one REJECTED_SHADOW record (one JSON line). NEVER raises.

    Expected caller fields (all optional — we log what we get):
        signal_id, symbol, direction ("BUY"/"SELL"), signal_time (ISO),
        entry_price, sl_dist, tp_dist, atr, regime, session, strategy,
        confidence, quality_score, reject_reason, gate  (which gate rejected)
    """
    try:
        if not _enabled():
            return False
        rec = dict(record or {})
        from core.trade_event_ledger import create_candidate_id
        candidate_id = str(rec.get("candidate_id") or create_candidate_id(
            symbol=str(rec.get("symbol") or ""),
            strategy=str(rec.get("strategy") or ""),
            signal=str(rec.get("direction") or ""),
            decision_bar_time=rec.get("decision_bar_time"),
        ))
        if candidate_id:
            rec["candidate_id"] = candidate_id
            rec["signal_id"] = candidate_id
        from core.data_quality import quarantine, stamp, validate_trade_record
        valid, reason = validate_trade_record(rec, require_rejection=True)
        if not valid:
            quarantine(rec, reason, _quarantine_path())
            return False
        stamp(rec)
        rec["record_type"] = "REJECTED_SHADOW"
        rec.setdefault("logged_at", _utc_now_iso())
        rec.setdefault("outcome", "PENDING")
        rec.setdefault("outcome_bar", None)
        rec.setdefault("outcome_resolved_at", None)

        path = log_path or _default_log_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        signal_id = str(rec.get("signal_id") or "")
        with _LEDGER_LOCK:
            known = _KNOWN_REJECTIONS.get(path)
            if known is None:
                known = set()
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as existing:
                        for line in existing:
                            try:
                                prior = json.loads(line)
                            except (TypeError, ValueError):
                                continue
                            if not isinstance(prior, dict):
                                continue
                            if prior.get("record_type") == "REJECTED_SHADOW":
                                prior_id = str(
                                    prior.get("candidate_id")
                                    or prior.get("signal_id")
                                    or ""
                                )
                                if prior_id:
                                    known.add(prior_id)
                                prior_candidate = create_candidate_id(
                                    symbol=str(prior.get("symbol") or ""),
                                    strategy=str(prior.get("strategy") or ""),
                                    signal=str(prior.get("direction") or ""),
                                    decision_bar_time=prior.get("decision_bar_time"),
                                )
                                if prior_candidate:
                                    known.add(prior_candidate)
                _KNOWN_REJECTIONS[path] = known
            if signal_id and signal_id in known:
                return True
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            if signal_id:
                known.add(signal_id)
        return True
    except Exception:
        return False


def log_virtual_shadow(record: Optional[Dict[str, Any]], *, log_path: Optional[str] = None) -> bool:
    """Append an accepted-but-not-executed Shadow candidate.

    These records use the same resolver contract as rejected signals, but are
    explicitly marked VIRTUAL_SHADOW so analytics can separate them.
    """
    try:
        if not _enabled():
            return False
        rec = dict(record or {})
        required = ("direction", "entry_price", "sl_dist", "tp_dist", "signal_time")
        if any(key not in rec for key in required):
            return False
        rec.setdefault("record_type", "VIRTUAL_SHADOW")
        from core.trade_event_ledger import create_candidate_id, append_candidate_record
        candidate_id = str(rec.get("candidate_id") or create_candidate_id(
            symbol=str(rec.get("symbol") or ""),
            strategy=str(rec.get("strategy") or ""),
            signal=str(rec.get("direction") or ""),
            decision_bar_time=rec.get("decision_bar_time"),
        ))
        if candidate_id:
            rec["candidate_id"] = candidate_id
            rec["signal_id"] = candidate_id
        rec.setdefault("logged_at", _utc_now_iso())
        rec.setdefault("outcome", "PENDING")
        rec.setdefault("outcome_bar", None)
        rec.setdefault("outcome_resolved_at", None)
        path = log_path or _default_log_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        if candidate_id:
            return append_candidate_record(path, rec)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def _quarantine_path() -> str:
    try:
        from core.settings import SHADOW_COUNTERFACTUAL_QUARANTINE_PATH
        return SHADOW_COUNTERFACTUAL_QUARANTINE_PATH
    except Exception:
        return "data/analytics/quarantine/rejected_shadow_invalid.jsonl"


# ---------------------------------------------------------------------------
# RESOLVE — fill outcomes for PENDING records from real candles
# ---------------------------------------------------------------------------

def _candle_time(c: Dict[str, Any]) -> str:
    return str(c.get("time") or c.get("timestamp") or "")


def _resolve_one(rec: Dict[str, Any], candles: List[Dict[str, Any]], horizon: int) -> Optional[Tuple[str, int]]:
    """Return (outcome, bars) or None if the record cannot be resolved.

    Conservative intrabar rule: if a single candle touches BOTH the SL and
    the TP level, we count it as a LOSS (worst case) — we never give the
    rejected signal the benefit of the doubt.
    """
    try:
        direction = str(rec.get("direction") or "").upper()
        entry = float(rec.get("entry_price") or 0)
        sl = float(rec.get("sl_dist") or 0)
        tp = float(rec.get("tp_dist") or 0)
        if entry <= 0 or sl <= 0 or tp <= 0 or direction not in ("BUY", "SELL"):
            return None

        if direction == "BUY":
            win_level, loss_level = entry + tp, entry - sl
        else:
            win_level, loss_level = entry - tp, entry + sl

        sig_t = str(rec.get("signal_time") or "")
        start = 0
        if sig_t:
            for i, c in enumerate(candles):
                if _candle_time(c) and _candle_time(c) > sig_t:
                    start = i
                    break
            else:
                return None  # no candle after the signal yet — still pending

        for j in range(start, min(start + horizon, len(candles))):
            c = candles[j]
            try:
                high = float(c["high"])
                low = float(c["low"])
            except (KeyError, TypeError, ValueError):
                continue
            hit_win = (high >= win_level) if direction == "BUY" else (low <= win_level)
            hit_loss = (low <= loss_level) if direction == "BUY" else (high >= loss_level)
            if hit_win and hit_loss:
                return ("LOSS_INTRABAR_AMBIGUOUS", j - start + 1)  # conservative
            if hit_loss:
                return ("LOSS", j - start + 1)
            if hit_win:
                return ("WIN", j - start + 1)

        if len(candles) - start >= horizon:
            return ("TIMEOUT", horizon)
        return None  # not enough bars yet
    except Exception:
        return None


def resolve_outcomes(candles: Optional[List[Dict[str, Any]]], *, log_path: Optional[str] = None,
                     horizon: Optional[int] = None) -> Dict[str, Any]:
    """Scan the ledger, resolve PENDING records against `candles`
    (list of {"time","high","low"} ascending), rewrite the file in place.
    Returns a small stats dict. NEVER raises.
    """
    try:
        path = log_path or _default_log_path()
        if not candles or not os.path.exists(path):
            return {"ok": False, "resolved": 0, "reason": "no candles or no ledger"}

        hz = horizon or _horizon()
        with open(path, "r", encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]

        resolved = 0
        for rec in records:
            if rec.get("outcome") != "PENDING":
                continue
            res = _resolve_one(rec, candles, hz)
            if res is None:
                continue
            rec["outcome"], rec["outcome_bar"] = res
            rec["outcome_resolved_at"] = _utc_now_iso()
            resolved += 1

        with open(path, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

        return {"ok": True, "resolved": resolved, "total": len(records)}
    except Exception:
        return {"ok": False, "resolved": 0, "reason": "exception"}


# ---------------------------------------------------------------------------
# READ — summary statistics (analytics only, never feeds live decisions)
# ---------------------------------------------------------------------------

def summary(*, log_path: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate the ledger. `ready=True` once resolved samples >= the
    configured minimum — before that, any conclusion is statistically void.
    NEVER raises."""
    try:
        path = log_path or _default_log_path()
        out: Dict[str, Any] = {
            "ok": False, "total": 0, "rejected_total": 0,
            "virtual_total": 0, "pending": 0,
            "WIN": 0, "LOSS": 0, "TIMEOUT": 0, "LOSS_INTRABAR_AMBIGUOUS": 0,
            "win_rate_rejected": None, "ready": False,
            "min_samples": _min_samples(),
            "unique_rejected_candidates": 0,
            "unidentified_rejected_records": 0,
            "conflicting_candidate_outcomes": 0,
            "by_rejection_reason": {},
            "by_entry_condition": {},
        }
        if not os.path.exists(path):
            out["ok"] = True
            return out

        with open(path, "r", encoding="utf-8") as fh:
            records = [json.loads(line) for line in fh if line.strip()]

        rejected_records = [
            rec for rec in records
            if rec.get("record_type", "REJECTED_SHADOW") == "REJECTED_SHADOW"
        ]
        out["total"] = len(records)
        out["rejected_total"] = len(rejected_records)
        unique_records: Dict[str, List[Dict[str, Any]]] = {}
        for rec in rejected_records:
            identity = _counterfactual_identity(rec)
            if identity is None:
                out["unidentified_rejected_records"] += 1
                continue
            unique_records.setdefault(identity, []).append(rec)
        resolved_records: List[Dict[str, Any]] = []
        for group in unique_records.values():
            terminal = {
                str(rec.get("outcome"))
                for rec in group
                if rec.get("outcome") in {
                    "WIN", "LOSS", "LOSS_INTRABAR_AMBIGUOUS", "TIMEOUT"
                }
            }
            if len(terminal) > 1:
                out["conflicting_candidate_outcomes"] += 1
                continue
            if terminal:
                outcome = next(iter(terminal))
                resolved_records.append(next(
                    rec for rec in group if rec.get("outcome") == outcome
                ))
            elif any(rec.get("outcome") == "PENDING" for rec in group):
                resolved_records.append(next(
                    rec for rec in group if rec.get("outcome") == "PENDING"
                ))
        out["unique_rejected_candidates"] = len(resolved_records)
        out["virtual_total"] = sum(
            rec.get("record_type") == "VIRTUAL_SHADOW" for rec in records
        )
        for rec in resolved_records:
            oc = rec.get("outcome")
            if oc == "PENDING":
                out["pending"] += 1
            elif oc in out:
                out[oc] += 1

        decided = out["WIN"] + out["LOSS"] + out["LOSS_INTRABAR_AMBIGUOUS"]
        if decided > 0:
            out["win_rate_rejected"] = round(out["WIN"] / decided, 4)
        resolved_count = len(resolved_records) - out["pending"]
        out["ready"] = resolved_count >= out["min_samples"]
        out["by_rejection_reason"] = _group_shadow_outcomes(
            resolved_records,
            lambda rec: [str(rec.get("reject_reason") or "UNKNOWN")],
            out["min_samples"],
        )
        out["by_entry_condition"] = _group_shadow_outcomes(
            resolved_records,
            _entry_conditions,
            out["min_samples"],
        )
        out["ok"] = True
        return out
    except Exception:
        return {"ok": False}


def _counterfactual_identity(record: Dict[str, Any]) -> Optional[str]:
    candidate_id = str(record.get("candidate_id") or "")
    if candidate_id:
        return f"candidate_id:{candidate_id}"
    if record.get("decision_bar_time") not in (None, ""):
        from core.trade_event_ledger import create_candidate_id
        candidate_id = create_candidate_id(
            symbol=str(record.get("symbol") or ""),
            strategy=str(record.get("strategy") or ""),
            signal=str(record.get("direction") or ""),
            decision_bar_time=record.get("decision_bar_time"),
        )
        if candidate_id:
            return f"candidate_id:{candidate_id}"
    signal_id = str(record.get("signal_id") or "")
    if not signal_id or signal_id.startswith("hb-"):
        return None
    return f"signal_id:{signal_id}"


def _entry_conditions(record: Dict[str, Any]) -> List[str]:
    values = record.get("entry_conditions") or []
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except (TypeError, ValueError):
            values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    return [str(value) for value in values if str(value)]


def _group_shadow_outcomes(
    records: List[Dict[str, Any]],
    key_values,
    min_samples: int,
) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        for key in set(key_values(record)):
            grouped.setdefault(key, []).append(record)

    result: Dict[str, Dict[str, Any]] = {}
    for key, group in grouped.items():
        counts = {
            outcome: sum(rec.get("outcome") == outcome for rec in group)
            for outcome in ("WIN", "LOSS", "LOSS_INTRABAR_AMBIGUOUS", "TIMEOUT", "PENDING")
        }
        decided = counts["WIN"] + counts["LOSS"] + counts["LOSS_INTRABAR_AMBIGUOUS"]
        resolved = len(group) - counts["PENDING"]
        result[key] = {
            "total": len(group),
            "resolved": resolved,
            **counts,
            "win_rate": round(counts["WIN"] / decided, 4) if decided else None,
            "samples_sufficient": resolved >= min_samples,
        }
    return result
