"""Analyze direction bias, rejection bias, and strategy coverage from clean ledgers."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_report(root: Path | None = None) -> Dict[str, Any]:
    root = root or Path(__file__).resolve().parents[1]
    from core.settings import SHADOW_COUNTERFACTUAL_LOG_PATH

    decision_path = root / "data/analytics/decision_ledger/decisions.jsonl"
    shadow_path = root / SHADOW_COUNTERFACTUAL_LOG_PATH
    entry_path = root / "data/analytics/entry_controller/entry_plans_2026-09-01-clean.jsonl"

    decisions = list(_read_jsonl(decision_path))
    shadow = list(_read_jsonl(shadow_path))
    entries = list(_read_jsonl(entry_path))

    direction_by_strategy = defaultdict(Counter)
    for row in decisions:
        direction_by_strategy[str(row.get("strategy") or "UNKNOWN")][str(row.get("direction") or "UNKNOWN")] += 1

    rejection_by_direction = Counter()
    rejection_by_reason = defaultdict(Counter)
    for row in shadow:
        direction = str(row.get("direction") or "UNKNOWN")
        reason = str(row.get("reject_reason") or "UNKNOWN")
        rejection_by_direction[direction] += 1
        rejection_by_reason[reason][direction] += 1

    strategy_coverage = Counter(str(row.get("strategy") or "UNKNOWN") for row in decisions)
    entry_status = Counter(str(row.get("status") or row.get("outcome") or "UNKNOWN") for row in entries)

    return {
        "decision_total": len(decisions),
        "direction_by_strategy": {k: dict(v) for k, v in direction_by_strategy.items()},
        "strategy_coverage": dict(strategy_coverage),
        "shadow_total": len(shadow),
        "shadow_rejection_by_direction": dict(rejection_by_direction),
        "shadow_rejection_by_reason": {k: dict(v) for k, v in rejection_by_reason.items()},
        "entry_total": len(entries),
        "entry_status": dict(entry_status),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
