# =============================================================================
# FER3ON — Portfolio Risk Authority: Impact Measurement
# =============================================================================
# السياق: evaluate_risk() (core/portfolio_risk_authority.py) كان موجودًا منذ
# v3.5 لكنه لم يُستدعَ من main.py على الإطلاق حتى إصلاح لاحق (انظر التعليق عند
# نقطة الاستدعاء في main.py — هذا هو السبب الجذري لحادثة 149 صفقة متزامنة).
# بعبارة أخرى: "النسخة القديمة" ليست خوارزمية بديلة يجب إعادة تنفيذها — هي
# ببساطة "بلا بوابة إطلاقًا": كل صفقة كانت تُنفَّذ باللوت/المخاطرة المطلوبة
# كما هي، بلا سقف تعرض إجمالي، بلا حد صفقات مفتوحة لكل استراتيجية، بلا وقف
# خسارة يومي مركزي. هذا الموديول يقيس فعليًا كم صفقة/كم نسبة مخاطرة كانت
# لتُنفَّذ تحت هذا السلوك القديم مقابل ما وافقت عليه/قصّته Authority الحقيقية
# فعليًا — رقميًا، وليس افتراضيًا.
#
# قياس فقط: record_risk_decision() لا تُغيّر القرار ولا تمنع صفقة؛ تُستدعى
# بعد evaluate_risk() الحقيقية في main.py وتسجّل
# ما حدث.
# =============================================================================

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

AUTHORITY_IMPACT_CSV = "data/analytics/authority_impact.csv"

_FIELDNAMES = [
    "logged_at",
    "strategy",
    "direction",
    "requested_risk_percent",
    "approved",
    "rejection_reason",
    "final_risk_percent",
    # تقديري فقط (من core.portfolio_risk_authority._round_lot_for_balance)،
    # لا يعكس اللوت الحقيقي الذي نُفِّذ به الأمر — راجع
    # core/risk_manager.py::calculate_smart_lot للرقم الحقيقي.
    "final_lot_estimate",
    "legacy_would_approve",
    "legacy_risk_percent",
    "risk_trimmed",
    "risk_percent_saved",
]


def _csv_path(csv_path: Optional[str] = None) -> str:
    return csv_path or AUTHORITY_IMPACT_CSV


def _ensure_csv(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()


def record_risk_decision(
    *,
    strategy: str,
    direction: str,
    requested_risk_percent: float,
    decision: Any,  # core.portfolio_risk_authority.RiskDecision
    csv_path: Optional[str] = None,
) -> bool:
    """Log one real Authority decision alongside what the pre-fix v3.5
    behavior (no gate called at all) would have done with the same
    candidate: approve it at the full requested risk, unconditionally.

    Never raises — call sites wrap this in the same "pure observability,
    can't disturb the real trade" pattern as analytics/execution_quality.py
    and analytics/tp_cap_monitor.py.
    """
    try:
        path = _csv_path(csv_path)
        _ensure_csv(path)

        requested = float(requested_risk_percent or 0)
        approved = bool(getattr(decision, "approved", False))
        final_risk = float(getattr(decision, "final_risk_percent", 0) or 0)
        final_lot_estimate = float(getattr(decision, "final_lot_estimate", 0) or 0)

        # Legacy (pre-fix) behavior: evaluate_risk() was never called, so
        # every candidate was approved at exactly the requested risk — no
        # exposure cap, no per-strategy cap, no daily-loss gate.
        legacy_risk = requested

        risk_trimmed = approved and final_risk < requested
        risk_percent_saved = round(requested - (final_risk if approved else 0.0), 4)

        row = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "strategy": strategy,
            "direction": direction,
            "requested_risk_percent": round(requested, 4),
            "approved": approved,
            "rejection_reason": getattr(decision, "rejection_reason", None) or "",
            "final_risk_percent": round(final_risk, 4),
            "final_lot_estimate": round(final_lot_estimate, 4),
            "legacy_would_approve": True,
            "legacy_risk_percent": round(legacy_risk, 4),
            "risk_trimmed": risk_trimmed,
            "risk_percent_saved": risk_percent_saved,
        }

        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writerow(row)
        return True
    except Exception as error:
        print(f"⚠️ AUTHORITY_IMPACT_LOG_FAILED (non-fatal): {error}")
        return False


def load_authority_decisions(csv_path: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _csv_path(csv_path)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def authority_impact_report(csv_path: Optional[str] = None) -> Dict[str, Any]:
    """Numeric answer to the report's ask: how many opportunities did the
    real, active Authority reject or trim that the old (never-called)
    v3.5 gate would have let through unfiltered?
    """
    rows = load_authority_decisions(csv_path)
    if not rows:
        return {
            "total_candidates": 0,
            "blocked_by_authority": 0,
            "blocked_by_reason": {},
            "trimmed_by_authority": 0,
            "total_risk_percent_prevented": 0.0,
            "by_strategy": {},
        }

    blocked_by_reason: Dict[str, int] = {}
    by_strategy: Dict[str, Dict[str, Any]] = {}
    blocked = 0
    trimmed = 0
    total_saved = 0.0

    for row in rows:
        strat = row.get("strategy", "UNKNOWN")
        bucket = by_strategy.setdefault(
            strat, {"candidates": 0, "blocked": 0, "trimmed": 0, "risk_percent_prevented": 0.0}
        )
        bucket["candidates"] += 1

        approved = str(row.get("approved", "")).strip().lower() == "true"
        saved = float(row.get("risk_percent_saved", 0) or 0)
        total_saved += saved
        bucket["risk_percent_prevented"] += saved

        if not approved:
            blocked += 1
            bucket["blocked"] += 1
            reason = row.get("rejection_reason") or "UNKNOWN"
            blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
        elif str(row.get("risk_trimmed", "")).strip().lower() == "true":
            trimmed += 1
            bucket["trimmed"] += 1

    for bucket in by_strategy.values():
        bucket["risk_percent_prevented"] = round(bucket["risk_percent_prevented"], 4)

    return {
        "total_candidates": len(rows),
        "blocked_by_authority": blocked,
        "blocked_by_reason": blocked_by_reason,
        "trimmed_by_authority": trimmed,
        "total_risk_percent_prevented": round(total_saved, 4),
        "by_strategy": by_strategy,
    }


def print_authority_impact_report(csv_path: Optional[str] = None) -> None:
    report = authority_impact_report(csv_path)
    print("=" * 70)
    print("PORTFOLIO RISK AUTHORITY — IMPACT vs. LEGACY (no-gate) BEHAVIOR")
    print("=" * 70)
    print(f"Total candidates evaluated : {report['total_candidates']}")
    print(f"Blocked (would have opened under legacy): {report['blocked_by_authority']}")
    for reason, count in sorted(report["blocked_by_reason"].items(), key=lambda kv: -kv[1]):
        print(f"    - {reason}: {count}")
    print(f"Trimmed (opened smaller than requested)  : {report['trimmed_by_authority']}")
    print(f"Total risk% prevented from exposure       : {report['total_risk_percent_prevented']}")
    print("-" * 70)
    for strat, bucket in report["by_strategy"].items():
        print(
            f"{strat:>8} | candidates={bucket['candidates']:>4} "
            f"blocked={bucket['blocked']:>4} trimmed={bucket['trimmed']:>4} "
            f"risk%_prevented={bucket['risk_percent_prevented']}"
        )
    print("=" * 70)


if __name__ == "__main__":
    print_authority_impact_report()
