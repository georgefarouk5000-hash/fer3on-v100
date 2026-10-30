"""Report whether enough post-recovery Shadow records exist for analysis."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def main() -> int:
    from core.settings import SHADOW_COUNTERFACTUAL_LOG_PATH

    path = Path(SHADOW_COUNTERFACTUAL_LOG_PATH)
    rows = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if path.exists() else []
    )
    recovery = [row for row in rows if row.get("config_revision") == "recovery_atr_v1"]
    outcomes = Counter(row.get("outcome", "PENDING") for row in recovery)
    decided = sum(outcomes[key] for key in ("WIN", "LOSS", "TIMEOUT", "LOSS_INTRABAR_AMBIGUOUS"))
    print(json.dumps({
        "path": str(path),
        "total_records": len(rows),
        "recovery_records": len(recovery),
        "recovery_outcomes": dict(outcomes),
        "recovery_decided": decided,
        "ready_for_recovery_analysis": decided >= 100,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
