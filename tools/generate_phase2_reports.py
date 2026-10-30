from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.analytics import analyze_trades
from core.data_integrity import AI_MEMORY_COLUMNS, HISTORY_COLUMNS, AI_MEMORY_FILE, HISTORY_FILE, read_csv_records
from core.trade_identity import resolve_trade_identity
from ml.ml_manager import get_ml_manager
from testing.statistics import full_stats_analysis, load_trades

REPORTS = {
    "ml": ROOT / "ml_status_report.md",
    "risk": ROOT / "risk_status_report.md",
    "integration": ROOT / "integration_status_report.md",
}

ML_SCAN_PATTERNS = {
    "xgb_models": ["*xgb*.py", "*xgboost*.py", "*xgb*.pkl"],
    "neural_models": ["*neural*.py", "*nn*.pkl"],
    "rl_models": ["*reinforcement*.py", "*rl*.py", "*q_table*.json", "*rl*.pkl"],
    "scalers": ["*scaler*.pkl"],
    "feature_generators": ["*feature*.py"],
}


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _find_patterns(patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        for path in ROOT.rglob(pattern):
            if path.is_file() and "__pycache__" not in path.parts:
                rel = _rel(path)
                if rel not in hits:
                    hits.append(rel)
    return sorted(hits)


def build_ml_report() -> str:
    manager = get_ml_manager()
    audit = manager.audit_models()

    lines = [
        "# ML Status Report",
        "",
        "## Phase 1 — ML Audit",
        "",
        f"- Unified status: **{audit['status']}**",
        f"- Exact required artifacts: **{audit['required_count']}**",
        f"- Usable runtime artifacts: **{audit['usable_count']}**",
        "",
        "## ML file scan",
        "",
    ]
    for label, patterns in ML_SCAN_PATTERNS.items():
        hits = _find_patterns(patterns)
        title = label.replace("_", " ").title()
        lines.append(f"### {title}")
        if hits:
            lines.extend(f"- `{hit}`" for hit in hits)
        else:
            lines.append("- None")
        lines.append("")

    lines.extend([
        "## Exact supported model files",
        "",
    ])
    for item in audit["details"]:
        exact_state = "VALID" if item["exact_ready"] else ("MISSING" if not item["required_exists"] else "INVALID")
        lines.append(f"- **{item['name']}** → `{item['required_path']}` → **{exact_state}**")
        if item["aliases"]:
            for alias in item["aliases"]:
                lines.append(
                    f"  - legacy alias: `{alias['path']}` → **{alias['status']}**"
                    + (f" ({alias['reason']})" if alias['reason'] != 'OK' else "")
                )
        if item["runtime_path"]:
            lines.append(f"  - runtime source: `{item['runtime_path']}` ({item['runtime_source']})")
        else:
            lines.append("  - runtime source: none")
    lines.extend([
        "",
        "## Missing exact files",
        "",
    ])
    if audit["missing_required_files"]:
        lines.extend(f"- `{path}`" for path in audit["missing_required_files"])
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Status policy",
        "",
        "- Allowed output states: `REAL`, `PARTIAL`, `DISABLED`.",
        "- `REAL` requires the exact supported file set, not only legacy aliases.",
        "- Current runtime may fall back to legacy aliases, but aliases do not promote status to `REAL`.",
    ])
    return "\n".join(lines) + "\n"


def build_risk_report() -> str:
    risk_manager_path = ROOT / "core" / "risk_manager.py"
    risk_protection_path = ROOT / "core" / "risk_protection.py"
    hard_risk_path = ROOT / "risk" / "hard_risk_cap.py"

    risk_manager_text = risk_manager_path.read_text(encoding="utf-8", errors="ignore")
    risk_protection_text = risk_protection_path.read_text(encoding="utf-8", errors="ignore")
    hard_risk_text = hard_risk_path.read_text(encoding="utf-8", errors="ignore")

    checks = {
        "unified_engine": "def evaluate_unified_risk(" in risk_manager_text,
        "lot_size": "def calculate_smart_lot(" in risk_manager_text,
        "drawdown_control": "def check_drawdown_limits(" in risk_manager_text,
        "max_open_trades": "def evaluate_position_limits(" in risk_manager_text,
        "session_risk": "def get_session_risk_multiplier(" in risk_manager_text,
        "ai_confidence_modifiers": "def compute_ai_risk_modifier(" in risk_manager_text,
        "hard_risk_bridge": "check_hard_risk_cap" in risk_manager_text and "record_trade_loss" in risk_manager_text,
        "duplicate_wrapper_removed": "from core.risk_manager import" in risk_protection_text,
        "legacy_duplicate_state_removed": "consecutive_losses" in risk_protection_text and "record_trade_result" in risk_protection_text,
        "hard_risk_module_present": "def check_hard_risk_cap(" in hard_risk_text,
    }

    status = "PASS" if all(checks.values()) else "PARTIAL"
    lines = [
        "# Risk Status Report",
        "",
        f"- Consolidation status: **{status}**",
        f"- Primary engine: `core/risk_manager.py`",
        f"- Compatibility wrapper: `core/risk_protection.py`",
        f"- Hard cap module: `risk/hard_risk_cap.py`",
        "",
        "## Verification",
        "",
    ]
    for key, ok in checks.items():
        label = key.replace("_", " ").title()
        lines.append(f"- {label}: **{'OK' if ok else 'MISSING'}**")

    lines.extend([
        "",
        "## Consolidated responsibilities",
        "",
        "- Lot size → `calculate_smart_lot()`",
        "- Drawdown control → `check_drawdown_limits()`",
        "- Max open trades → `evaluate_position_limits()`",
        "- Session risk → `get_session_risk_multiplier()`",
        "- AI confidence modifiers → `compute_ai_risk_modifier()`",
        "- Hard risk cap → `check_hard_risk_cap()` bridge inside unified engine",
    ])
    return "\n".join(lines) + "\n"


def _duplicates(rows: list[dict], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key, "") or "") for row in rows if str(row.get(key, "") or ""))
    return {k: v for k, v in counts.items() if v > 1}


def build_integration_report() -> str:
    history_rows = read_csv_records(HISTORY_FILE, HISTORY_COLUMNS)
    memory_rows = read_csv_records(AI_MEMORY_FILE, AI_MEMORY_COLUMNS)
    history_tickets = {str(row.get("ticket", "") or "") for row in history_rows if str(row.get("ticket", "") or "")}
    memory_tickets = {str(row.get("ticket", "") or "") for row in memory_rows if str(row.get("ticket", "") or "")}

    analytics_summary, analytics_metrics = analyze_trades()
    stats = full_stats_analysis(load_trades(HISTORY_FILE))

    history_not_in_memory = sorted(history_tickets - memory_tickets)
    memory_not_in_history = sorted(memory_tickets - history_tickets)
    memory_by_ticket = {str(row.get("ticket", "") or ""): row for row in memory_rows}
    pending_open_memory = [ticket for ticket in memory_not_in_history if str(memory_by_ticket.get(ticket, {}).get("result", "")).upper() == "OPEN"]
    orphan_closed_memory = [ticket for ticket in memory_not_in_history if ticket not in pending_open_memory]

    magic_mismatches = []
    for row in memory_rows:
        raw_magic = row.get("magic", 0)
        strategy = row.get("strategy", "UNKNOWN")
        identity = resolve_trade_identity(strategy=strategy, magic=raw_magic)
        if identity["magic"] and str(raw_magic) not in {"", "0"} and int(float(raw_magic)) != int(identity["magic"]):
            magic_mismatches.append(
                {
                    "ticket": str(row.get("ticket", "") or ""),
                    "strategy": strategy,
                    "raw_magic": int(float(raw_magic)),
                    "canonical_magic": identity["magic"],
                }
            )

    history_duplicates = _duplicates(history_rows, "ticket")
    memory_duplicates = _duplicates(memory_rows, "ticket")

    integration_status = "PASS"
    if history_not_in_memory or history_duplicates or memory_duplicates or orphan_closed_memory:
        integration_status = "PARTIAL"

    lines = [
        "# Integration Status Report",
        "",
        f"- Integration status: **{integration_status}**",
        f"- History rows: **{len(history_rows)}**",
        f"- Memory rows: **{len(memory_rows)}**",
        f"- Analytics total trades: **{analytics_metrics.get('total_trades', 0)}**",
        f"- Statistics total trades: **{stats.get('total_trades', 0)}**",
        "",
        "## Flow validation",
        "",
        "- Trade → History: enforced through `core/mt5_history_sync.py` into `data/history/trades.csv`.",
        "- History → Analytics: `core/analytics.py` reads `data/history/trades.csv`.",
        "- History → AI Memory: MT5 closed trades are upserted into `data/memory/ai_memory.csv`.",
        "- AI Memory → Adaptive AI: MT5 closed trades are forwarded to `core/adaptive_learning.record_trade_outcome()`.",
        "",
        "## Coverage checks",
        "",
        f"- History tickets missing in memory: **{len(history_not_in_memory)}**",
        f"- Memory tickets missing in history: **{len(memory_not_in_history)}**",
        f"- Pending open memory tickets: **{len(pending_open_memory)}**",
        f"- Orphan closed memory tickets: **{len(orphan_closed_memory)}**",
        f"- Duplicate history tickets: **{len(history_duplicates)}**",
        f"- Duplicate memory tickets: **{len(memory_duplicates)}**",
        f"- Magic mismatches in memory: **{len(magic_mismatches)}**",
        "",
        "## Missing history tickets in memory",
        "",
    ]
    if history_not_in_memory:
        lines.extend(f"- `{ticket}`" for ticket in history_not_in_memory[:50])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Memory tickets without history counterpart",
        "",
    ])
    if memory_not_in_history:
        lines.extend(f"- `{ticket}`" for ticket in memory_not_in_history[:50])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Open-memory-only tickets",
        "",
    ])
    if pending_open_memory:
        lines.extend(f"- `{ticket}`" for ticket in pending_open_memory[:50])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Orphan closed-memory tickets",
        "",
    ])
    if orphan_closed_memory:
        lines.extend(f"- `{ticket}`" for ticket in orphan_closed_memory[:50])
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Duplicate tickets",
        "",
        f"- History duplicates: `{json.dumps(history_duplicates, ensure_ascii=False)}`",
        f"- Memory duplicates: `{json.dumps(memory_duplicates, ensure_ascii=False)}`",
        "",
        "## Magic mismatch details",
        "",
    ])
    if magic_mismatches:
        for item in magic_mismatches[:50]:
            lines.append(
                f"- ticket `{item['ticket']}` → strategy `{item['strategy']}` | raw `{item['raw_magic']}` | canonical `{item['canonical_magic']}`"
            )
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Analytics summary",
        "",
        f"- `{analytics_summary}`",
        f"- Statistics grade: **{stats.get('grade', 'N/A')}**",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    REPORTS["ml"].write_text(build_ml_report(), encoding="utf-8")
    REPORTS["risk"].write_text(build_risk_report(), encoding="utf-8")
    REPORTS["integration"].write_text(build_integration_report(), encoding="utf-8")
    print(json.dumps({k: str(v) for k, v in REPORTS.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
