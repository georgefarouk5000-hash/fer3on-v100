# =============================================================================
# FER3ON AI V2 — DECISION AUTHORITY FACADE
# =============================================================================
# Single runtime authority entrypoint.
# All upstream engines remain evidence producers only.
# =============================================================================

from typing import Any, Dict

from core.unified_bridge import (
    build_decision_context as _build_decision_context,
    decision_to_legacy_format,
)
from core.unified_decision import (
    DecisionContext,
    DecisionResult,
    format_decision_log,
    unified_decide,
)


def build_decision_context(*args, **kwargs) -> DecisionContext:
    """Build a normalized decision context for FER3ON AI V2."""
    return _build_decision_context(*args, **kwargs)


def decide_trade(ctx: DecisionContext) -> DecisionResult:
    """Single runtime authority for trade approval / rejection / sizing."""
    return unified_decide(ctx)


def decision_to_runtime_format(result: DecisionResult) -> Dict[str, Any]:
    """Backward-compatible runtime payload with FER3ON AI V2 branding."""
    payload = decision_to_legacy_format(result)
    payload["authority"] = "FER3ON AI V2 Decision Authority"
    return payload


def format_authority_log(result: DecisionResult) -> str:
    """Runtime-safe, V2-branded authority log."""
    return (
        format_decision_log(result)
        .replace("[V7]", "[FER3ON AI V2]")
        .replace("FER3ON V7", "FER3ON AI V2")
        .replace("FER3ON AI V1", "FER3ON AI V2")
    )
