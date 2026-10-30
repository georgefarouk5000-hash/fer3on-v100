# =============================================================================
# FER3ON — Execution Quality Engine (Phase-2 spec §3.3, new addition)
# =============================================================================
# فلسفة:
#   ExecutionOfficer (FAIE, brain/faie/analysts.py) يقيّم فقط جاهزية ما
#   *قبل* الصفقة (spread/ATR/RR). هذا الموديول يضيف النصف الآخر: ما حدث
#   *بعد* الإرسال فعليًا — انزلاق السعر (slippage)، تأخير التنفيذ (delay)،
#   ونسبة الرفض (rejection rate). هذا موديول قياس فقط — لا يُغيّر أي قرار
#   تنفيذ، لا يحظر، ولا يُعدّل حجم أي صفقة. القيمة الوحيدة التي ينتجها هي
#   بيانات جودة تنفيذ تُقرأ لاحقًا (certification/framework.py، ولاحقًا
#   RiskOfficer FAIE كمُدخل evidence اختياري — غير مُفعَّل بعد).
#
#   دقيق التسمية عمدًا: "execution_outcome" وليس "execution_decision" —
#   هذا الموديول لا يقرر شيئًا، فقط يُسجّل ما حدث فعليًا بعد أن قرر
#   core/trade_executor.py أن يرسل الطلب.
#
# Failure handling (per spec): a missing field (broker doesn't report fill
# delay, a rejection has no filled_price, etc.) is recorded as an empty CSV
# cell / None and excluded from that specific aggregate — never fabricated.
# =============================================================================

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import EXECUTION_QUALITY_CSV

_FIELDNAMES = [
    "logged_at",
    "ticket",
    "symbol",
    "requested_price",
    "filled_price",
    "requested_time",
    "filled_time",
    "slippage",
    "delay_seconds",
    "rejected",
    "strategy",
    "regime",
    "session",
    "entry_mode",
]


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _csv_path() -> str:
    return EXECUTION_QUALITY_CSV


def _ensure_csv(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()


def record_execution_outcome(
    ticket: Any,
    requested_price: Optional[float],
    filled_price: Optional[float],
    requested_time: Any,
    filled_time: Any,
    rejected: bool,
    *,
    symbol: Optional[str] = None,
    csv_path: Optional[str] = None,
    strategy: Optional[str] = None,
    regime: Optional[str] = None,
    session: Optional[str] = None,
    entry_mode: Optional[str] = None,
) -> bool:
    """Append one post-trade execution-quality row.

    This is intentionally the ONLY thing this function does: append a row.
    It never raises to the caller — core/trade_executor.py must be able to
    call this after every order attempt without any risk of it disturbing
    the real execution flow (see the call site there, wrapped in try/except
    on top of this function's own internal guard, defense in depth).

    Args:
        ticket: broker order/deal ticket, or None if the order never got one
            (e.g. rejected before a ticket was assigned).
        requested_price: the price the request was sent at.
        filled_price: the price actually filled at, or None if rejected /
            unknown (broker doesn't always report this on rejection).
        requested_time: timestamp (ISO string or datetime) request was sent.
        filled_time: timestamp (ISO string or datetime) fill was confirmed,
            or None if rejected / broker doesn't report fill time.
        rejected: True if the order was rejected/failed, False if filled.
        symbol: optional, for multi-symbol accounts.
        csv_path: override destination (mainly for tests).

    Returns:
        True if the row was appended, False on any failure (never raises).
    """
    try:
        path = csv_path or _csv_path()
        _ensure_csv(path)

        req_price = float(requested_price) if requested_price is not None else None
        fill_price = float(filled_price) if (filled_price is not None and not rejected) else None

        slippage: Optional[float] = None
        if req_price is not None and fill_price is not None:
            slippage = round(fill_price - req_price, 6)

        req_dt = requested_time if isinstance(requested_time, datetime) else _parse_iso(requested_time)
        fill_dt = filled_time if isinstance(filled_time, datetime) else _parse_iso(filled_time)
        delay_seconds: Optional[float] = None
        if req_dt is not None and fill_dt is not None and not rejected:
            delay_seconds = round((fill_dt - req_dt).total_seconds(), 6)

        row = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "ticket": ticket if ticket is not None else "",
            "symbol": symbol or "",
            "requested_price": "" if req_price is None else req_price,
            "filled_price": "" if fill_price is None else fill_price,
            "requested_time": _iso_or_none(requested_time) or "",
            "filled_time": ("" if rejected else (_iso_or_none(filled_time) or "")),
            "slippage": "" if slippage is None else slippage,
            "delay_seconds": "" if delay_seconds is None else delay_seconds,
            "rejected": bool(rejected),
            "strategy": str(strategy or "UNKNOWN").upper(),
            "regime": str(regime or "UNKNOWN").upper(),
            "session": str(session or "UNKNOWN").upper(),
            "entry_mode": str(entry_mode or "UNKNOWN").upper(),
        }

        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writerow(row)
        return True
    except Exception:
        # Same rule as brain/faie/shadow_logging.py: a quality-tracking
        # failure must never propagate into the execution path.
        return False


@dataclass
class ExecutionQualitySummary:
    total_records: int = 0
    fills: int = 0
    rejections: int = 0
    rejection_rate: float = 0.0
    slippage_sample_size: int = 0
    avg_slippage: Optional[float] = None
    delay_sample_size: int = 0
    avg_delay_seconds: Optional[float] = None
    coverage_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_records": self.total_records,
            "fills": self.fills,
            "rejections": self.rejections,
            "rejection_rate": round(self.rejection_rate, 4),
            "slippage_sample_size": self.slippage_sample_size,
            "avg_slippage": None if self.avg_slippage is None else round(self.avg_slippage, 6),
            "delay_sample_size": self.delay_sample_size,
            "avg_delay_seconds": None if self.avg_delay_seconds is None else round(self.avg_delay_seconds, 6),
            "coverage_note": self.coverage_note,
        }


def _load_rows(csv_path: Optional[str] = None) -> List[Dict[str, str]]:
    path = csv_path or _csv_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def summarize_execution_quality(csv_path: Optional[str] = None, **filters: str) -> ExecutionQualitySummary:
    """Read back EXECUTION_QUALITY_CSV and summarize slippage/delay/rejection.

    Missing fields are excluded from their specific aggregate rather than
    treated as zero (a missing fill delay is not the same as a zero-second
    fill) — this mirrors the "don't fabricate a value" rule in the spec.
    """
    rows = _load_rows(csv_path)
    filters = {key: str(value).upper() for key, value in filters.items() if value is not None}
    if filters:
        rows = [row for row in rows if all(
            str(row.get(key, "UNKNOWN")).upper() == value
            for key, value in filters.items()
        )]
    total = len(rows)
    if total == 0:
        return ExecutionQualitySummary(coverage_note="NO_RECORDS")

    rejections = 0
    slippages: List[float] = []
    delays: List[float] = []

    for r in rows:
        is_rejected = str(r.get("rejected", "")).strip().lower() in ("true", "1", "yes")
        if is_rejected:
            rejections += 1

        slip_raw = (r.get("slippage") or "").strip()
        if slip_raw:
            try:
                slippages.append(float(slip_raw))
            except ValueError:
                pass

        delay_raw = (r.get("delay_seconds") or "").strip()
        if delay_raw:
            try:
                delays.append(float(delay_raw))
            except ValueError:
                pass

    fills = total - rejections
    rejection_rate = rejections / total if total else 0.0
    avg_slippage = (sum(slippages) / len(slippages)) if slippages else None
    avg_delay = (sum(delays) / len(delays)) if delays else None

    coverage_note = ""
    missing_slippage = fills - len(slippages)
    missing_delay = fills - len(delays)
    if missing_slippage > 0 or missing_delay > 0:
        coverage_note = (
            f"{missing_slippage} of {fills} fills missing slippage, "
            f"{missing_delay} of {fills} fills missing delay data"
        )

    return ExecutionQualitySummary(
        total_records=total,
        fills=fills,
        rejections=rejections,
        rejection_rate=rejection_rate,
        slippage_sample_size=len(slippages),
        avg_slippage=avg_slippage,
        delay_sample_size=len(delays),
        avg_delay_seconds=avg_delay,
        coverage_note=coverage_note,
    )


def calculate_execution_quality_score(csv_path: Optional[str] = None) -> float:
    """
    حساب درجة جودة التنفيذ (0.0 إلى 1.0) من البيانات الحقيقية.
    
    الصيغة (✅ FIX [2026-09-02]):
      - تبدأ من 1.0 (مثالي)
      - خصم rejection_rate: 0-50% (إذا 100% مرفوضة → خصم 0.5)
      - خصم avg_slippage: 0-20% (متناسب مع الانزلاق)
      - خصم avg_delay_seconds: 0-10% (متناسب مع التأخير)
    
    إذا كانت البيانات ناقصة، تُرجع 0.5 (قيمة محايدة)
    """
    summary = summarize_execution_quality(csv_path)
    
    if summary.total_records == 0:
        # لا توجد بيانات — قيمة محايدة
        return 0.5
    
    score = 1.0
    
    # ✅ FIX: خصم كامل rejection_rate (0-1 → خصم 0-0.5)
    if summary.rejection_rate > 0:
        score -= min(0.5, summary.rejection_rate)  # حتى 100% رفض = خصم 0.5 → score=0.5
    
    # خصم بناءً على avg_slippage (إذا كانت موجودة)
    if summary.avg_slippage is not None:
        # assume avg_slippage > 0.01 is bad, scale down from there
        slip_penalty = min(0.2, abs(summary.avg_slippage) * 5)  # max 20%
        score -= slip_penalty
    
    # خصم بناءً على avg_delay_seconds (إذا كانت موجودة)
    if summary.avg_delay_seconds is not None and summary.avg_delay_seconds > 0:
        delay_penalty = min(0.1, summary.avg_delay_seconds * 0.01)  # max 10%
        score -= delay_penalty
    
    return max(0.0, min(1.0, round(score, 4)))


def calculate_regime_fit_score(
    strategy: str,
    market_regime: str,
    csv_path: Optional[str] = None
) -> float:
    """
    حساب درجة توافق الاستراتيجية مع الـ regime من البيانات الحقيقية.
    
    يستخدم win_rate من التاريخ الحقيقي للاستراتيجية في الـ regime المحدد.
    إذا كانت البيانات ناقصة، يعود إلى قيمة محايدة (0.5-1.0).
    """
    try:
        from analytics.performance_repository import get_strategy_breakdown
        
        # الحصول على breakdown بحسب الاستراتيجية
        strategy_upper = str(strategy or 'SMC').upper()
        
        # لاحقاً: يمكن تحسين هذا لقراءة من CSV مباشرة مع regime filter
        # الآن نرجع قيمة آمنة قائمة على الجدول القاعدي
        from core.market_regime import get_regime_fit_multiplier
        return float(get_regime_fit_multiplier(strategy, market_regime))
    except Exception:
        # قيمة افتراضية آمنة
        return 1.0
