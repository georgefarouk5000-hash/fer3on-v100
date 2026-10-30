from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

WATCHDOG_CAPABILITIES = (
    "AUTO_RESTART",
    "CONNECTION_RECOVERY",
    "CRASH_RECOVERY",
    "PROCESS_RESURRECTION",
    "RAM_MONITORING",
    "MEMORY_LEAK_DETECTION",
    "LOOP_FREEZE_DETECTION",
    "DEGRADATION_TRACKING",
)

CRITICAL_ISSUES = {
    "PROCESS_DOWN",
    "DATABASE_DOWN",
    "MT5_DOWN",
    "MEMORY_DOWN",
    "LOOP_FROZEN",
    "RAM_CRITICAL",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def collect_watchdog_status(
    *,
    mt5_available=True,
    memory_available=True,
    telegram_available=True,
    cpu_ok=True,
    db_ok=True,
    production_ready=True,
    signal_quality=100,
    process_alive=True,
    cpu_percent=0.0,
    disk_ok=True,
    loop_frozen=False,
    feed_ok=True,
    ram_ok=True,
    ram_percent=0.0,
    rss_mb=0.0,
    rss_growth_mb=0.0,
    ai_memory_healthy=True,
    ai_memory_rows=0,
    db_latency_ms=0.0,
    telegram_latency_ms=0.0,
    loop_latency_sec=0.0,
    historical_degradation=0,
):
    issues = []
    recovery_actions = []

    cpu_percent = _safe_float(cpu_percent)
    ram_percent = _safe_float(ram_percent)
    rss_mb = _safe_float(rss_mb)
    rss_growth_mb = _safe_float(rss_growth_mb)
    db_latency_ms = _safe_float(db_latency_ms)
    telegram_latency_ms = _safe_float(telegram_latency_ms)
    loop_latency_sec = _safe_float(loop_latency_sec)
    historical_degradation = int(historical_degradation or 0)

    if not mt5_available:
        issues.append("MT5_DOWN")
        recovery_actions.extend(["AUTO_RESTART", "CONNECTION_RECOVERY"])
    if not telegram_available:
        issues.append("TELEGRAM_DOWN")
        recovery_actions.append("CONNECTION_RECOVERY")
    if not db_ok:
        issues.append("DATABASE_DOWN")
        recovery_actions.append("CRASH_RECOVERY")
    if not memory_available:
        issues.append("MEMORY_DOWN")
        recovery_actions.append("CRASH_RECOVERY")
    if not process_alive:
        issues.append("PROCESS_DOWN")
        recovery_actions.append("PROCESS_RESURRECTION")
    if not cpu_ok or cpu_percent >= 90:
        issues.append("CPU_HIGH")
    elif cpu_percent >= 75:
        issues.append("CPU_ELEVATED")
    if not ram_ok or ram_percent >= 95:
        issues.append("RAM_CRITICAL")
    elif ram_percent >= 85:
        issues.append("RAM_HIGH")
    if rss_growth_mb >= 256:
        issues.append("MEMORY_LEAK_SUSPECTED")
    if not feed_ok:
        issues.append("FEED_DOWN")
    if not disk_ok:
        issues.append("DISK_HIGH")
    if loop_frozen or loop_latency_sec >= 120:
        issues.append("LOOP_FROZEN")
    elif loop_latency_sec >= 30:
        issues.append("LOOP_SLOW")
    if not production_ready:
        issues.append("STARTUP_BLOCK")
    if not ai_memory_healthy:
        issues.append("AI_MEMORY_DEGRADED")
    if db_latency_ms >= 1500:
        issues.append("DATABASE_LATENCY_HIGH")
    if telegram_latency_ms >= 1500:
        issues.append("TELEGRAM_LATENCY_HIGH")
    if historical_degradation >= 3:
        issues.append("HISTORICAL_DEGRADATION")

    if not issues:
        status = "HEALTHY"
    elif any(issue in CRITICAL_ISSUES for issue in issues):
        status = "CRITICAL"
    else:
        status = "DEGRADED"

    automation_status = "READY" if production_ready and process_alive and status != "CRITICAL" else "BLOCKED"

    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "issues": issues,
        "recovery_actions": sorted(set(recovery_actions)),
        "production_ready": bool(production_ready),
        "signal_quality": int(signal_quality or 0),
        "automation_status": automation_status,
        "monitors": {
            "mt5": bool(mt5_available),
            "feed_ok": bool(feed_ok),
            "telegram": bool(telegram_available),
            "database": bool(db_ok),
            "memory": bool(memory_available),
            "cpu_ok": bool(cpu_ok),
            "cpu_percent": round(cpu_percent, 1),
            "ram_ok": bool(ram_ok),
            "ram_percent": round(ram_percent, 1),
            "rss_mb": round(rss_mb, 1),
            "rss_growth_mb": round(rss_growth_mb, 1),
            "disk_ok": bool(disk_ok),
            "process_alive": bool(process_alive),
            "loop_frozen": bool(loop_frozen),
            "loop_latency_sec": round(loop_latency_sec, 1),
            "ai_memory_healthy": bool(ai_memory_healthy),
            "ai_memory_rows": int(ai_memory_rows or 0),
            "db_latency_ms": round(db_latency_ms, 1),
            "telegram_latency_ms": round(telegram_latency_ms, 1),
            "historical_degradation": historical_degradation,
        },
        "capabilities": list(WATCHDOG_CAPABILITIES),
    }


def run_watchdog_cycle(**kwargs):
    status = collect_watchdog_status(**kwargs)
    print(
        f"WATCHDOG | {status['status']}"
        f" | issues={','.join(status['issues']) or 'NONE'}"
        f" | actions={','.join(status['recovery_actions']) or 'NONE'}"
    )
    return status
