from typing import Any, Dict, Optional

from core.execution_optimizer_v2 import optimize_order_execution


def build_execution_plan(
    *,
    decision: Dict[str, Any],
    signal: str,
    strategy: str,
    exec_quality: Dict[str, Any],
    ml_result: Dict[str, Any],
    session: str,
    atr: float,
    rr_ratio: float,
    tick: Optional[Any] = None,
    symbol_info: Optional[Any] = None,
) -> Dict[str, Any]:
    """Convert a decision into an execution plan with risk and routing parameters."""
    approved = bool(decision.get("approved", True))
    if not approved:
        return {
            "approved": False,
            "reason": decision.get("reason", "DECISION_BLOCKED"),
            "mode": "BLOCKED",
            "score": 0,
            "deviation": 20,
            "filling_type": None,
            "filling_name": "IOC",
            "lot_multiplier": 0.0,
            "comment_tag": "EXEC_BLOCK",
        }

    execution = optimize_order_execution(
        symbol=decision.get("symbol", "XAUUSD"),
        signal=signal,
        exec_quality=exec_quality,
        ml_result=ml_result,
        session=session,
        atr=atr,
        rr_ratio=rr_ratio,
        tick=tick,
        symbol_info=symbol_info,
    )
    execution.setdefault("strategy", strategy)
    execution.setdefault("decision_mode", decision.get("mode", "UNKNOWN"))
    return execution
