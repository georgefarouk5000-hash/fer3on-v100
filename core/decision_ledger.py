# =============================================================================
# FER3ON — PHASE 4 | DECISION LEDGER + TRUTH ATTRIBUTION
# =============================================================================
# Every decision (signal -> authority -> entry plan -> SL/TP -> management ->
# exit -> result) is recorded ONCE, immutably, tagged with BUILD_ID, regime,
# session, and the REASON for the decision. Later, outcomes (WIN/LOSS, MFE,
# MAE) are ATTACHED to the same signal_id — so attribution is always to the
# build/regime/session that actually produced the decision, never guessed.
#
# SAFETY CONTRACT (same family as analytics/shadow_counterfactual.py):
#   - LOGGING ONLY. Nothing here is ever read back into the live decision
#     path. No function may change, delay, or block a real decision.
#   - Every public function NEVER raises. All failure modes are swallowed
#     and reported through return values only.
#   - Imports NO execution code: no MetaTrader5, no core.trade_executor.
# =============================================================================
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LEDGER_SCHEMA_VERSION = "4.0"


# ---------------------------------------------------------------------------
# Config access (defensive — a missing setting must never break logging)
# ---------------------------------------------------------------------------

def _cfg(name: str, default: Any) -> Any:
    try:
        import core.settings as _s
        return getattr(_s, name, default)
    except Exception:
        return default


def _enabled() -> bool:
    return bool(_cfg("DECISION_LEDGER_ENABLED", True))


def _log_path() -> str:
    return str(_cfg("DECISION_LEDGER_LOG_PATH",
                    "data/analytics/decision_ledger/decisions.jsonl"))


def _outcomes_path() -> str:
    return str(_cfg("DECISION_LEDGER_OUTCOMES_PATH",
                    "data/analytics/decision_ledger/outcomes.jsonl"))


def _build_id() -> str:
    return str(_cfg("BUILD_ID", "UNKNOWN_BUILD"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: str, record: Dict[str, Any]) -> bool:
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception:
        return False


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        if not os.path.exists(path):
            return out
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_decision(record: Dict[str, Any]) -> bool:
    """Record one decision event. Enriches with build_id / schema / ts.
    `record` should carry whatever the caller has: signal_id, symbol,
    direction, strategy, regime, session, stage (SIGNAL|AUTHORITY|ENTRY|
    SLTP|MANAGEMENT|EXIT), decision (APPROVE|REJECT|WAIT|...), reason,
    confidence, quality_score, mode (LIVE|SHADOW|DEMO), entry/sl/tp, ...
    """
    if not _enabled():
        return False
    try:
        if not isinstance(record, dict):
            return False
        rec = dict(record)
        rec.setdefault("signal_id", f"ledger-{_utc_now_iso()}")
        rec["build_id"] = _build_id()
        rec["schema_version"] = LEDGER_SCHEMA_VERSION
        rec["logged_at"] = _utc_now_iso()
        rec.setdefault("mode", "SHADOW")
        return _append_jsonl(_log_path(), rec)
    except Exception:
        return False


def attach_outcome(signal_id: str, outcome: Dict[str, Any]) -> bool:
    """Attach the realised outcome to a previously logged decision.
    outcome: result (WIN|LOSS|TIMEOUT|BE), pnl, mfe, mae, exit_reason,
    bars_held, tp1_reached, tp2_reached, sl_reached, ...
    Attribution fields (build_id of the ORIGINAL decision) are copied so
    learning never mixes builds.
    """
    if not _enabled():
        return False
    try:
        if not signal_id or not isinstance(outcome, dict):
            return False
        rec = dict(outcome)
        rec["signal_id"] = str(signal_id)
        decisions = _read_jsonl(_log_path())
        original = next(
            (item for item in reversed(decisions)
             if str(item.get("signal_id")) == str(signal_id)),
            None,
        )
        rec["build_id_at_decision"] = (
            original.get("build_id") if original else _build_id()
        )
        if original:
            rec.setdefault(
                "decision_snapshot_id",
                original.get("decision_snapshot_id"),
            )
        rec["outcome_logged_at"] = _utc_now_iso()
        rec["schema_version"] = LEDGER_SCHEMA_VERSION
        return _append_jsonl(_outcomes_path(), rec)
    except Exception:
        return False


def get_ledger_records(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        recs = _read_jsonl(_log_path())
        return recs[-limit:] if limit else recs
    except Exception:
        return []


def get_outcomes(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        recs = _read_jsonl(_outcomes_path())
        return recs[-limit:] if limit else recs
    except Exception:
        return []


def truth_attribution_stats(min_samples: int = 1) -> Dict[str, Any]:
    """Aggregate outcomes per (strategy, session, regime, build_id).
    This is the ONLY legitimate input for learning: outcomes attributed to
    the exact build + context that produced them. Buckets with fewer than
    `min_samples` outcomes are reported but flagged insufficient.
    """
    stats: Dict[str, Any] = {"buckets": {}, "total_outcomes": 0}
    try:
        decisions = {r.get("signal_id"): r for r in _read_jsonl(_log_path())}
        for oc in _read_jsonl(_outcomes_path()):
            sid = oc.get("signal_id")
            dec = decisions.get(sid, {})
            key = "|".join(str(x or "UNKNOWN") for x in (
                dec.get("strategy"), dec.get("session"),
                dec.get("regime"), dec.get("build_id",
                                          oc.get("build_id_at_decision"))))
            b = stats["buckets"].setdefault(key, {
                "n": 0, "wins": 0, "losses": 0, "pnl": 0.0,
                "mfe_sum": 0.0, "mae_sum": 0.0, "insufficient": True})
            b["n"] += 1
            res = str(oc.get("result", "")).upper()
            if res == "WIN":
                b["wins"] += 1
            elif res == "LOSS":
                b["losses"] += 1
            try:
                b["pnl"] += float(oc.get("pnl", 0) or 0)
                b["mfe_sum"] += float(oc.get("mfe", 0) or 0)
                b["mae_sum"] += float(oc.get("mae", 0) or 0)
            except Exception:
                pass
            stats["total_outcomes"] += 1
        for b in stats["buckets"].values():
            b["insufficient"] = b["n"] < max(1, int(min_samples))
            b["win_rate"] = round(b["wins"] / b["n"], 4) if b["n"] else 0.0
            b["avg_mfe"] = round(b["mfe_sum"] / b["n"], 4) if b["n"] else 0.0
            b["avg_mae"] = round(b["mae_sum"] / b["n"], 4) if b["n"] else 0.0
            b["pnl"] = round(b["pnl"], 2)
    except Exception:
        pass
    return stats
