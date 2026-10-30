# =============================================================================
# FER3ON — TP Capping Validation Telemetry
# =============================================================================
# السياق: TP_CAPPING_IMPLEMENTATION_REPORT.md يوثّق أن ميزة TP Capping
# (core/settings.py: get_tp_cap_multiplier/get_tp_sl_multiplier، مُطبَّقة في
# main.py::_build_order_request::
# _build_order_request_generic) جاهزة ومُفعَّلة فعليًا وبدون شرط — لكن التقرير
# نفسه يوصي باختبارها على بيانات حية لأسبوعين على الأقل قبل الاعتماد الكامل
# على أرقامها. المشكلة: لم يكن هناك أي تسجيل لعدد مرات التفعيل الفعلي ولا
# لحجم القص — أي "اختبار حي" كان سيعتمد على قراءة سطور print() من اللوج
# يدويًا. هذا الموديول قياس فقط (نفس فلسفة analytics/execution_quality.py):
# لا يُغيّر أي قرار تنفيذ ولا يمنع صفقة، فقط يسجّل متى قصّت الميزة TP فعليًا
# وبكم، حتى تكون فترة الاختبار الحية قابلة للقياس بأرقام حقيقية.
# =============================================================================

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import TP_CAP_MONITOR_CSV

_FIELDNAMES = [
    "logged_at",
    "strategy",
    "signal",
    "atr",
    "sl_dist",
    "tp_dist_requested",
    "tp_dist_capped",
    "clip_pct",
    "cap_multiplier_atr",
    "cap_multiplier_sl",
]


def _csv_path(csv_path: Optional[str] = None) -> str:
    return csv_path or TP_CAP_MONITOR_CSV


def _ensure_csv(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()


def record_tp_cap_event(
    *,
    strategy: str,
    signal: str,
    atr: float,
    sl_dist: float,
    tp_dist_requested: float,
    tp_dist_capped: float,
    cap_multiplier_atr: float,
    cap_multiplier_sl: float,
    csv_path: Optional[str] = None,
) -> bool:
    """Append one row every time the TP cap actually clips a TP.

    Only called when tp_dist_requested > tp_dist_capped (see call sites in
    main.py) — an uncapped trade never appears
    in this log, so "rows in this file" already answers "how often does it
    trigger". Never raises: a logging failure here must never be able to
    turn into a blocked or malformed trade.
    """
    try:
        path = _csv_path(csv_path)
        _ensure_csv(path)

        requested = float(tp_dist_requested or 0)
        capped = float(tp_dist_capped or 0)
        clip_pct = round((1 - (capped / requested)) * 100, 2) if requested > 0 else 0.0

        row = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "strategy": strategy,
            "signal": signal,
            "atr": round(float(atr or 0), 5),
            "sl_dist": round(float(sl_dist or 0), 5),
            "tp_dist_requested": round(requested, 5),
            "tp_dist_capped": round(capped, 5),
            "clip_pct": clip_pct,
            "cap_multiplier_atr": cap_multiplier_atr,
            "cap_multiplier_sl": cap_multiplier_sl,
        }

        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writerow(row)
        return True
    except Exception as error:
        print(f"⚠️ TP_CAP_MONITOR_LOG_FAILED (non-fatal): {error}")
        return False


def load_tp_cap_events(csv_path: Optional[str] = None) -> List[Dict[str, Any]]:
    path = _csv_path(csv_path)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def tp_cap_summary(csv_path: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate view for the recommended live-validation window: how often
    the cap fires per strategy and the average/max clip size. Does NOT try
    to join against trade outcomes — that join belongs in a dedicated
    analysis pass once ai_memory.csv reliably has tp_dist per ticket (see
    the ai_memory enrichment fix), not duplicated here.
    """
    events = load_tp_cap_events(csv_path)
    if not events:
        return {"total_events": 0, "by_strategy": {}}

    by_strategy: Dict[str, Dict[str, Any]] = {}
    for event in events:
        strat = event.get("strategy", "UNKNOWN")
        bucket = by_strategy.setdefault(strat, {"count": 0, "clip_pct_sum": 0.0, "clip_pct_max": 0.0})
        bucket["count"] += 1
        try:
            clip = float(event.get("clip_pct", 0) or 0)
        except Exception:
            clip = 0.0
        bucket["clip_pct_sum"] += clip
        bucket["clip_pct_max"] = max(bucket["clip_pct_max"], clip)

    for strat, bucket in by_strategy.items():
        bucket["clip_pct_avg"] = round(bucket["clip_pct_sum"] / bucket["count"], 2) if bucket["count"] else 0.0
        del bucket["clip_pct_sum"]

    return {"total_events": len(events), "by_strategy": by_strategy}
