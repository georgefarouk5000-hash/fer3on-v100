import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.settings import ANALYTICS_DIR


DEFAULT_METRICS_FILE = os.path.join(ANALYTICS_DIR, "production_metrics.json")


def _ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


def compute_signal_quality_score(
    *,
    composite_score: float,
    recent_wr: float,
    recent_expectancy: float,
    execution_quality: float,
    outcome: Optional[str] = None,
) -> float:
    """Compute a production-grade signal quality score from multiple signals."""
    outcome_bonus = 0.0
    if outcome and str(outcome).lower() in {"win", "profit", "success"}:
        outcome_bonus = 8.0
    elif outcome and str(outcome).lower() in {"loss", "lose", "fail"}:
        outcome_bonus = -10.0

    composite_component = max(0.0, min(100.0, float(composite_score or 0)))
    wr_component = max(0.0, min(100.0, float(recent_wr or 0) * 100.0))
    expectancy_component = max(0.0, min(100.0, (float(recent_expectancy or 0) + 2.0) * 20.0))
    execution_component = max(0.0, min(100.0, float(execution_quality or 0)))

    score = (
        composite_component * 0.35
        + wr_component * 0.25
        + expectancy_component * 0.20
        + execution_component * 0.20
        + outcome_bonus
    )
    return round(max(0.0, min(100.0, score)), 2)


def update_signal_quality_metrics(
    *,
    strategy: str,
    signal: str,
    composite_score: float,
    recent_wr: float,
    recent_expectancy: float,
    execution_quality: float,
    outcome: Optional[str] = None,
    metrics_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a signal-quality entry and return the latest metrics summary."""
    path = metrics_path or DEFAULT_METRICS_FILE
    _ensure_parent(path)

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    else:
        state = {}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "signal": signal,
        "composite_score": round(float(composite_score or 0), 2),
        "recent_wr": round(float(recent_wr or 0), 3),
        "recent_expectancy": round(float(recent_expectancy or 0), 3),
        "execution_quality": round(float(execution_quality or 0), 2),
        "outcome": str(outcome or "unknown"),
        "signal_quality": compute_signal_quality_score(
            composite_score=composite_score,
            recent_wr=recent_wr,
            recent_expectancy=recent_expectancy,
            execution_quality=execution_quality,
            outcome=outcome,
        ),
    }

    history = list(state.get("history", []))
    history.append(entry)
    state["history"] = history[-200:]
    state["latest_signal_quality"] = entry["signal_quality"]
    state["latest_outcome"] = entry["outcome"]
    state["updated_at"] = int(time.time())

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return entry


def evaluate_production_readiness(*, recent_wr: float, recent_expectancy: float, max_drawdown: float, signal_quality: float, open_risk: float) -> Dict[str, Any]:
    """Return a simple production risk assessment for live trading."""
    safe_to_trade = (
        float(recent_wr or 0) >= 0.50
        and float(recent_expectancy or 0) >= 0.2
        and float(max_drawdown or 0) <= 5.0
        and float(signal_quality or 0) >= 65.0
        and float(open_risk or 0) <= 0.5
    )

    if not safe_to_trade:
        risk_level = "HIGH"
    elif float(signal_quality or 0) >= 80.0:
        risk_level = "LOW"
    else:
        risk_level = "MEDIUM"

    return {
        "safe_to_trade": safe_to_trade,
        "risk_level": risk_level,
        "recent_wr": round(float(recent_wr or 0), 3),
        "recent_expectancy": round(float(recent_expectancy or 0), 3),
        "max_drawdown": round(float(max_drawdown or 0), 2),
        "signal_quality": round(float(signal_quality or 0), 2),
        "open_risk": round(float(open_risk or 0), 3),
    }


def build_production_metrics_snapshot(*, recent_wr: float, recent_expectancy: float, max_drawdown: float, signal_quality: float, open_risk: float) -> Dict[str, Any]:
    readiness = evaluate_production_readiness(
        recent_wr=recent_wr,
        recent_expectancy=recent_expectancy,
        max_drawdown=max_drawdown,
        signal_quality=signal_quality,
        open_risk=open_risk,
    )
    return {
        "win_rate": round(float(recent_wr or 0) * 100.0, 1),
        "expectancy": round(float(recent_expectancy or 0), 3),
        "max_drawdown": round(float(max_drawdown or 0), 2),
        "signal_quality": round(float(signal_quality or 0), 2),
        "open_risk": round(float(open_risk or 0), 3),
        "safe_to_trade": readiness["safe_to_trade"],
        "risk_level": readiness["risk_level"],
    }


def write_production_dashboard(*, snapshot: Dict[str, Any], output_path: Optional[str] = None) -> Dict[str, Any]:
    """Write a Markdown dashboard summarizing production readiness and automation health."""
    path = output_path or os.path.join(ANALYTICS_DIR, "production_dashboard.md")
    _ensure_parent(path)

    safe_state = bool(snapshot.get("safe_to_trade", False))
    risk_level = str(snapshot.get("risk_level", "HIGH"))
    lines = [
        "# PRODUCTION AUTOMATION DASHBOARD",
        "",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- Safe to Trade: {'YES' if safe_state else 'NO'}",
        f"- Risk Level: {risk_level}",
        "",
        "## Core Metrics",
        f"- Win Rate: {snapshot.get('win_rate', 0)}%",
        f"- Expectancy: {snapshot.get('expectancy', 0)}",
        f"- Max Drawdown: {snapshot.get('max_drawdown', 0)}%",
        f"- Signal Quality: {snapshot.get('signal_quality', 0)}",
        f"- Open Risk: {snapshot.get('open_risk', 0)}",
        "",
        "## Automation Status",
        "- Signal quality scoring: ENABLED",
        "- Result-based learning: ENABLED",
        "- Production safety gate: ENABLED",
        "- Dashboard export: READY",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {"dashboard_file": path, "safe_to_trade": safe_state, "risk_level": risk_level}


def refresh_production_dashboard(*, recent_wr: float, recent_expectancy: float, max_drawdown: float, signal_quality: float, open_risk: float, output_path: Optional[str] = None) -> Dict[str, Any]:
    """Build a snapshot and export the production dashboard in one step."""
    snapshot = build_production_metrics_snapshot(
        recent_wr=recent_wr,
        recent_expectancy=recent_expectancy,
        max_drawdown=max_drawdown,
        signal_quality=signal_quality,
        open_risk=open_risk,
    )
    result = write_production_dashboard(snapshot=snapshot, output_path=output_path)
    result.update(snapshot)
    return result


def compute_ai_cooperation_score(*, memory_score: float, ml_score: float, brain_score: float, dna_score: float, execution_score: float, smc_score: float) -> float:
    """Compute a simple cooperation score between advisory modules."""
    values = [
        float(memory_score or 0),
        float(ml_score or 0),
        float(brain_score or 0),
        float(dna_score or 0),
        float(execution_score or 0),
        float(smc_score or 0),
    ]
    score = round(sum(values) / len(values), 2)
    return max(0.0, min(100.0, score))


def evaluate_demo_certification(*, trades: int, win_rate: float, profit_factor: float, drawdown: float, recovery_time: int) -> Dict[str, Any]:
    """Evaluate whether a demo run satisfies the documented certification thresholds."""
    passed = (
        int(trades or 0) >= 100
        and float(win_rate or 0) >= 0.50
        and float(profit_factor or 0) >= 1.20
        and float(drawdown or 0) <= 10.0
        and int(recovery_time or 0) <= 30
    )
    return {
        "passed": passed,
        "trades": int(trades or 0),
        "win_rate": round(float(win_rate or 0), 3),
        "profit_factor": round(float(profit_factor or 0), 3),
        "drawdown": round(float(drawdown or 0), 2),
        "recovery_time": int(recovery_time or 0),
    }


def evaluate_promotion_requirements(*, trades: int, win_rate: float, profit_factor: float, drawdown: float, recovery_time: int, authority_leaks: bool, broken_chains: bool, critical_failures: int) -> Dict[str, Any]:
    """Evaluate whether the system satisfies promotion requirements."""
    passed = (
        int(trades or 0) >= 200
        and float(win_rate or 0) >= 0.55
        and float(profit_factor or 0) >= 1.40
        and float(drawdown or 0) <= 10.0
        and int(recovery_time or 0) <= 20
        and not authority_leaks
        and not broken_chains
        and int(critical_failures or 0) == 0
    )
    return {
        "passed": passed,
        "trades": int(trades or 0),
        "win_rate": round(float(win_rate or 0), 3),
        "profit_factor": round(float(profit_factor or 0), 3),
        "drawdown": round(float(drawdown or 0), 2),
        "recovery_time": int(recovery_time or 0),
        "authority_leaks": bool(authority_leaks),
        "broken_chains": bool(broken_chains),
        "critical_failures": int(critical_failures or 0),
    }
