# =============================================================================
# FAIE — Phase 3: Shadow-Logging Helper (Phase-2 spec §5)
# =============================================================================
# CONSTITUTIONAL NOTICE: this module is the single call site allowed to run
# ChiefDecisionOfficer next to a REAL decision cycle. It is still subject to
# every rule in docs/FAIE/VOLUME_1_CONSTITUTION.md:
#   - LOGGING ONLY. Nothing here is read back into the real decision path.
#   - log_faie_shadow_decision() must NEVER raise and must NEVER be able to
#     change, delay, or block the real decision it is logging next to. Every
#     failure mode (bad ctx, disk full, import error, whatever) is swallowed
#     and reported through the return value only.
#   - This module does not import trade_executor / execution_optimizer_v2 /
#     MetaTrader5 / any order-sending code, same as the rest of brain/faie —
#     see tests/faie/test_faie_master_brain.py::test_no_execution_capability,
#     extended in tests/faie/test_shadow_logging.py for this file specifically.
# =============================================================================

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.unified_decision import DecisionContext
from .chief_decision_officer import ChiefDecisionOfficer, Decision
from .personality import get_profile


def _default_log_path() -> str:
    try:
        from core.settings import FAIE_SHADOW_LOG_PATH
        return FAIE_SHADOW_LOG_PATH
    except Exception:
        # Defensive fallback only — core.settings should always have this
        # once §5 is wired in. Never let a missing setting break logging.
        return "data/faie/shadow_log.jsonl"


def build_shadow_decision(ctx: DecisionContext) -> Decision:
    """Run the FAIE Chief Decision Officer on `ctx`, using the Market
    Personality Engine (§3.1) profile for ctx.symbol. Pure computation,
    no I/O — split out from log_faie_shadow_decision so callers/tests can
    get the Decision object without touching disk.
    """
    cdo = ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))
    return cdo.decide(ctx)


def log_faie_shadow_decision(
    ctx: DecisionContext,
    *,
    candidate_id: Optional[str] = None,
    real_decision_summary: Optional[Dict[str, Any]] = None,
    log_path: Optional[str] = None,
) -> bool:
    """Append one JSON line with the FAIE shadow Decision for `ctx`.

    Args:
        ctx: the same DecisionContext the real decision cycle already built.
        real_decision_summary: optional small dict describing what
            unified_decide() actually chose (decision/composite_score/
            risk_multiplier are enough — NOT the full DecisionResult object,
            to keep this helper decoupled from that dataclass's shape). This
            is what lets §6's backtest harness later compute agreement_rate
            without re-deriving it from two separate log files.
        log_path: override the destination path (mainly for tests).

    Returns:
        True if a line was successfully appended, False on ANY failure.
        Never raises — that is the entire point of this helper (see the
        constitutional notice above and PHASE_2_SPECIFICATION.md §5's
        failure-handling rule, which calls this "the single most important
        failure-handling rule in this whole document").
    """
    try:
        decision = build_shadow_decision(ctx)

        row: Dict[str, Any] = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "symbol": getattr(ctx, "symbol", None),
            "strategy": getattr(ctx, "strategy", None),
            "signal": getattr(ctx, "signal", None),
            "candidate_id": candidate_id,
            "faie_decision": decision.to_dict(),
        }
        if real_decision_summary is not None:
            row["real_decision_summary"] = real_decision_summary

        path = log_path or _default_log_path()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        from core.trade_event_ledger import append_candidate_record
        return append_candidate_record(path, row)
    except Exception:
        # Deliberately broad and deliberately silent to the caller's
        # control flow: a FAIE logging failure must never surface as an
        # exception in the real decision path. Callers that want visibility
        # can inspect the boolean return value.
        return False
