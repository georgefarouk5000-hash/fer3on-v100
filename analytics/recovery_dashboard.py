# =========================================
# FER3ON AI V2 — PERFORMANCE ANALYTICS DASHBOARD
# Tracks recovery module effectiveness
# =========================================

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    V7_PLUS_ENABLED,
    V7_RECOVERY_DASHBOARD_ENABLED,
    ANALYTICS_DIR,
)

METRICS_FILE = os.path.join(ANALYTICS_DIR, "RECOVERY_METRICS.json")
DASHBOARD_FILE = os.path.join(ANALYTICS_DIR, "RECOVERY_DASHBOARD.md")
TRADES_LOG = os.path.join(ANALYTICS_DIR, "recovery_trades.json")


def _ensure_dirs() -> None:
    os.makedirs(ANALYTICS_DIR, exist_ok=True)


def _load_json(path: str, default: Any) -> Any:
    _ensure_dirs()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    _ensure_dirs()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _win_rate(trades: List[Dict[str, Any]], filter_key: str = None, filter_val: str = None) -> float:
    subset = trades
    if filter_key and filter_val is not None:
        subset = [t for t in trades if str(t.get(filter_key, "")).upper() == str(filter_val).upper()]
    if not subset:
        return 0.0
    wins = sum(1 for t in subset if str(t.get("result", "")).upper() == "WIN")
    return round(wins / len(subset) * 100, 2)


def _avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def record_recovery_trade(
    strategy: str,
    direction: str,
    result: str,
    profit: float,
    confidence: float,
    duration_minutes: float = 0.0,
    session: str = "UNKNOWN",
    entry_type: str = "NORMAL",
    smc_score: float = 0.0,
    velocity_bonus: float = 0.0,
    micro_trigger: bool = False,
    scale_in: bool = False,
    opportunistic: bool = False,
) -> None:
    """Record a trade for dashboard analytics."""
    if not V7_PLUS_ENABLED or not V7_RECOVERY_DASHBOARD_ENABLED:
        return

    trades = _load_json(TRADES_LOG, [])
    trades.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "direction": direction,
        "result": str(result or "UNKNOWN").upper(),
        "profit": round(float(profit or 0), 2),
        "confidence": round(float(confidence or 0), 2),
        "duration_minutes": round(float(duration_minutes or 0), 1),
        "session": session,
        "entry_type": entry_type,
        "smc_score": smc_score,
        "velocity_bonus": velocity_bonus,
        "micro_trigger": bool(micro_trigger),
        "scale_in": bool(scale_in),
        "opportunistic": bool(opportunistic),
    })
    if len(trades) > 2000:
        trades = trades[-2000:]
    _save_json(TRADES_LOG, trades)


def compute_recovery_metrics(
    missed_opportunity_stats: Optional[Dict[str, Any]] = None,
    trades: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Compute aggregate recovery metrics.
    """
    missed_opportunity_stats = missed_opportunity_stats or {}
    trades = trades if trades is not None else _load_json(TRADES_LOG, [])

    false_rate = float(missed_opportunity_stats.get("false_rejection_rate", 0) or 0)
    missed_score = float(missed_opportunity_stats.get("missed_opportunity_score", 50) or 0)

    opp_trades = [t for t in trades if t.get("opportunistic")]
    scale_trades = [t for t in trades if t.get("scale_in")]
    micro_trades = [t for t in trades if t.get("micro_trigger")]
    smc_trades = [t for t in trades if float(t.get("smc_score", 0) or 0) > 0]
    velocity_trades = [t for t in trades if float(t.get("velocity_bonus", 0) or 0) > 0]

    profits = [float(t.get("profit", 0) or 0) for t in trades]
    confidences = [float(t.get("confidence", 0) or 0) for t in trades]
    durations = [float(t.get("duration_minutes", 0) or 0) for t in trades if t.get("duration_minutes")]
    losses = [p for p in profits if p < 0]

    session_wr = {}
    for sess in ("ASIA", "LONDON", "NEWYORK", "OVERLAP", "OFF_HOURS"):
        session_wr[sess] = _win_rate(trades, "session", sess)

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "false_rejection_rate": false_rate,
        "missed_opportunity_score": missed_score,
        "total_trades": len(trades),
        "opportunity_engine_win_rate": _win_rate(opp_trades),
        "scale_in_win_rate": _win_rate(scale_trades),
        "micro_trigger_win_rate": _win_rate(micro_trades),
        "smc_win_rate": _win_rate(smc_trades),
        "velocity_bonus_win_rate": _win_rate(velocity_trades),
        "session_win_rates": session_wr,
        "average_confidence": _avg(confidences),
        "average_trade_duration_minutes": _avg(durations),
        "average_profit": _avg(profits),
        "average_drawdown": round(abs(_avg(losses)), 2) if losses else 0.0,
        "total_profit": round(sum(profits), 2),
        "total_wins": sum(1 for t in trades if str(t.get("result", "")).upper() == "WIN"),
        "total_losses": sum(1 for t in trades if str(t.get("result", "")).upper() == "LOSS"),
    }
    return metrics


def generate_dashboard_markdown(metrics: Dict[str, Any]) -> str:
    """Generate RECOVERY_DASHBOARD.md content."""
    lines = [
        "# FER3ON AI V2 Dashboard",
        "",
        f"*Generated: {metrics.get('generated_at', 'N/A')}*",
        "",
        "## Missed Opportunity",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| False Rejection Rate | {metrics.get('false_rejection_rate', 0)}% |",
        f"| Missed Opportunity Score | {metrics.get('missed_opportunity_score', 50)} |",
        "",
        "## Module Win Rates",
        "",
        f"| Module | Win Rate |",
        f"|--------|----------|",
        f"| Opportunity Engine | {metrics.get('opportunity_engine_win_rate', 0)}% |",
        f"| Scale-In | {metrics.get('scale_in_win_rate', 0)}% |",
        f"| Micro Trigger | {metrics.get('micro_trigger_win_rate', 0)}% |",
        f"| SMC | {metrics.get('smc_win_rate', 0)}% |",
        f"| Velocity Bonus | {metrics.get('velocity_bonus_win_rate', 0)}% |",
        "",
        "## Session Win Rates",
        "",
        f"| Session | Win Rate |",
        f"|---------|----------|",
    ]

    for sess, wr in (metrics.get("session_win_rates") or {}).items():
        lines.append(f"| {sess} | {wr}% |")

    lines.extend([
        "",
        "## Performance Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Trades | {metrics.get('total_trades', 0)} |",
        f"| Average Confidence | {metrics.get('average_confidence', 0)} |",
        f"| Average Duration (min) | {metrics.get('average_trade_duration_minutes', 0)} |",
        f"| Average Profit | {metrics.get('average_profit', 0)} |",
        f"| Average Drawdown | {metrics.get('average_drawdown', 0)} |",
        f"| Total Profit | {metrics.get('total_profit', 0)} |",
        "",
        "---",
        "*FER3ON AI V2 — auto-generated dashboard*",
    ])
    return "\n".join(lines)


def update_recovery_dashboard(
    missed_opportunity_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate RECOVERY_METRICS.json and RECOVERY_DASHBOARD.md.
    """
    if not V7_PLUS_ENABLED or not V7_RECOVERY_DASHBOARD_ENABLED:
        return {"enabled": False, "reason": "DISABLED"}

    metrics = compute_recovery_metrics(missed_opportunity_stats)
    _save_json(METRICS_FILE, metrics)

    md = generate_dashboard_markdown(metrics)
    _ensure_dirs()
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(md)

    print(
        f"[RECOVERY+] DASHBOARD: updated"
        f" | trades={metrics['total_trades']}"
        f" | false_rate={metrics['false_rejection_rate']}%"
        f" | avg_conf={metrics['average_confidence']}"
    )

    return {
        "enabled": True,
        "metrics": metrics,
        "metrics_file": METRICS_FILE,
        "dashboard_file": DASHBOARD_FILE,
    }
