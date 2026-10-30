# =============================================================================
# FAIE — Historical Backtest Harness (Phase-2 spec §6)
# =============================================================================
# فلسفة ومحاذير صريحة (يجب قراءتها قبل الوثوق بأي نتيجة من هذا الملف):
#
#   الوثيقة الأصلية (PHASE_2_SPECIFICATION.md §6) افترضت أن testing/backtester.py
#   يُعيد تشغيل تسلسلات DecisionContext تاريخية جاهزة. بعد فحص الكود فعليًا:
#   testing/backtester.py لا يفعل ذلك — هو يعمل على مصفوفات أسعار OHLC خام من
#   MT5 (`rates`) ويولّد إشاراته الخاصة داخليًا؛ لا يوجد ولا سطر واحد فيه يبني
#   DecisionContext. لم يتم أبدًا تخزين DecisionContext تاريخي كامل لأي صفقة
#   سابقة — فقط نتيجتها النهائية (data/history/trades.csv).
#
#   لذلك هذا المُشغّل يعيد بناء نسخة جزئية *بأفضل جهد ممكن* من DecisionContext
#   لكل صفقة تاريخية، من الحقول الموجودة فعليًا في data/history/trades.csv
#   (signal, strategy, session, market_regime, rr_ratio, quality_score,
#   brain_score) فقط. أي حقل آخر في DecisionContext (atr_value, spread_ratio,
#   smc_strength, liquidity_strength...) يبقى على قيمته الافتراضية في
#   dataclass نفسه — أي "لا دليل" بالنسبة لأي محلل يقرأه، وليس قيمة مُلفَّقة.
#
#   كذلك: لا يوجد سجل تاريخي لما قرره unified_decide() فعليًا لكل صفقة (فقط
#   الإشارة والنتيجة النهائية). لذلك "القرار الحقيقي" هنا هو proxy: الاتجاه
#   (BUY/SELL) الذي أُرسل فعليًا للسوق، وليس إعادة بناء كاملة لحالة
#   unified_decide() الداخلية. هذا محدود لكنه صادق — أفضل من التظاهر بدقة
#   غير موجودة. راجع docs/FAIE/PHASE_2_PROGRESS.md للتفاصيل الكاملة.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.data_integrity import read_csv_records
from core.unified_decision import DecisionContext
from brain.faie.chief_decision_officer import ChiefDecisionOfficer
from brain.faie.evidence import BULLISH, BEARISH, NEUTRAL
from brain.faie.personality import get_profile

DEFAULT_HISTORY_CSV = "data/history/trades.csv"

# Below this many evaluated rows, the report is directionally suggestive at
# best — flag it rather than let a human read false confidence into it.
MIN_ROWS_FOR_CONFIDENT_REPORT = 20

_SIGNAL_TO_DIRECTION = {"BUY": BULLISH, "SELL": BEARISH}


def _row_to_decision_context(row: Dict[str, Any]) -> Optional[DecisionContext]:
    """Best-effort DecisionContext from one trades.csv row.

    Returns None (row must be skipped, counted in skipped_rows) if the row
    lacks the two fields with no safe fallback: a real BUY/SELL signal and
    a real strategy name. Everything else either has a legitimate row
    value or is left at DecisionContext's own dataclass default, which is
    the same "no evidence" state any other caller producing a partial
    context already relies on — never a fabricated realistic-looking value.
    """
    signal = str(row.get("signal", "")).upper().strip()
    strategy = str(row.get("strategy", "")).upper().strip()
    if signal not in ("BUY", "SELL") or not strategy or strategy == "UNKNOWN":
        return None

    kwargs: Dict[str, Any] = {"strategy": strategy, "signal": signal}

    market_regime = str(row.get("market_regime", "") or "").upper().strip()
    if market_regime:
        kwargs["market_regime"] = market_regime

    session = str(row.get("session", "") or "").upper().strip()
    if session:
        kwargs["session"] = session

    for field_name in ("rr_ratio", "quality_score", "brain_score"):
        raw = row.get(field_name)
        try:
            if raw not in (None, ""):
                kwargs[field_name] = float(raw)
        except (TypeError, ValueError):
            continue

    return DecisionContext(**kwargs)


@dataclass
class FaieBacktestReport:
    total_rows: int = 0
    skipped_rows: int = 0
    evaluated_rows: int = 0

    agreements: int = 0
    opposite_disagreements: int = 0
    neutral_calls: int = 0
    agreement_rate: float = 0.0

    disagreement_cases: List[Dict[str, Any]] = field(default_factory=list)
    would_have_avoided_losses: List[Dict[str, Any]] = field(default_factory=list)
    would_have_missed_wins: List[Dict[str, Any]] = field(default_factory=list)

    status: str = "NO_DATA"  # NO_DATA | INSUFFICIENT_DATA | OK
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "skipped_rows": self.skipped_rows,
            "evaluated_rows": self.evaluated_rows,
            "agreements": self.agreements,
            "opposite_disagreements": self.opposite_disagreements,
            "neutral_calls": self.neutral_calls,
            "agreement_rate": round(self.agreement_rate, 4),
            "disagreement_cases": self.disagreement_cases,
            "would_have_avoided_losses": self.would_have_avoided_losses,
            "would_have_missed_wins": self.would_have_missed_wins,
            "status": self.status,
            "note": self.note,
        }


def run_faie_backtest(
    history_rows: Optional[List[Dict[str, Any]]] = None,
    *,
    csv_path: Optional[str] = None,
    max_disagreement_cases: int = 200,
) -> FaieBacktestReport:
    """Replay historical trade rows through ChiefDecisionOfficer and compare
    FAIE's directional lean against the direction actually traded.

    Args:
        history_rows: pre-loaded rows (mainly for tests) — same shape
            core.data_integrity.read_csv_records returns. If omitted,
            rows are loaded from `csv_path` (default: data/history/trades.csv).
        csv_path: override the CSV source when history_rows isn't given.
        max_disagreement_cases: cap on how many individual case dicts are
            kept, to keep the report a bounded size for very long histories;
            the aggregate counts (agreements/disagreements/rates) are never
            capped, only the example lists are.

    Returns:
        FaieBacktestReport. Never raises — a row FAIE's analysts can't use
        is skipped and counted, not filled with fabricated data (see
        _row_to_decision_context and the module docstring above).
    """
    if history_rows is None:
        history_rows = read_csv_records(csv_path or DEFAULT_HISTORY_CSV)

    report = FaieBacktestReport(total_rows=len(history_rows))

    if not history_rows:
        report.status = "NO_DATA"
        report.note = f"no rows found (looked in {csv_path or DEFAULT_HISTORY_CSV})"
        return report

    for row in history_rows:
        ctx = _row_to_decision_context(row)
        if ctx is None:
            report.skipped_rows += 1
            continue

        try:
            cdo = ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))
            decision = cdo.decide(ctx)
        except Exception as exc:
            # A row FAIE's own pipeline can't process is a skip, not a
            # crash of the whole backtest — same failure-handling rule as
            # everywhere else in FAIE.
            report.skipped_rows += 1
            continue

        report.evaluated_rows += 1
        actual_direction = _SIGNAL_TO_DIRECTION.get(str(row.get("signal", "")).upper().strip())
        faie_direction = decision.top_scenario.direction

        agrees = faie_direction == actual_direction
        is_neutral = faie_direction == NEUTRAL

        if agrees:
            report.agreements += 1
        elif is_neutral:
            report.neutral_calls += 1
        else:
            report.opposite_disagreements += 1

        actual_result = str(row.get("result", "")).upper().strip()
        actual_profit = row.get("profit")
        try:
            actual_profit = float(actual_profit) if actual_profit not in (None, "") else None
        except (TypeError, ValueError):
            actual_profit = None

        case = {
            "ticket": row.get("ticket"),
            "date": row.get("date"),
            "strategy": ctx.strategy,
            "actual_signal": row.get("signal"),
            "actual_result": actual_result or "UNKNOWN",
            "actual_profit": actual_profit,
            "faie_direction": faie_direction,
            "faie_confidence": round(decision.confidence, 2),
        }

        if not agrees and len(report.disagreement_cases) < max_disagreement_cases:
            report.disagreement_cases.append(case)

        # Only rows with a realized outcome (not still OPEN) can say
        # anything about what FAIE "would have" avoided or missed.
        if actual_result == "LOSS" and not agrees:
            if len(report.would_have_avoided_losses) < max_disagreement_cases:
                report.would_have_avoided_losses.append(case)
        elif actual_result == "WIN" and not agrees:
            if len(report.would_have_missed_wins) < max_disagreement_cases:
                report.would_have_missed_wins.append(case)

    if report.evaluated_rows > 0:
        report.agreement_rate = report.agreements / report.evaluated_rows

    if report.evaluated_rows == 0:
        report.status = "NO_DATA"
        report.note = "every row was skipped — no row had both a BUY/SELL signal and a real strategy name"
    elif report.evaluated_rows < MIN_ROWS_FOR_CONFIDENT_REPORT:
        report.status = "INSUFFICIENT_DATA"
        report.note = (
            f"only {report.evaluated_rows} evaluated rows (below the "
            f"{MIN_ROWS_FOR_CONFIDENT_REPORT}-row confidence floor) — "
            "treat agreement_rate as directional, not conclusive"
        )
    else:
        report.status = "OK"
        report.note = (
            f"{report.skipped_rows} of {report.total_rows} rows skipped "
            "(missing signal/strategy) — see module docstring for what this "
            "report can and cannot claim given available historical data"
        )

    return report


def run_faie_backtest_by_period(
    csv_path: Optional[str] = None,
    *,
    history_rows: Optional[List[Dict[str, Any]]] = None,
    period_labels: Optional[List[str]] = None,
    n_periods: int = 2,
) -> Dict[str, Dict[str, Any]]:
    """Split history rows into `n_periods` chronological chunks (assumes
    the source CSV is already in chronological order, true for
    data/history/trades.csv) and run run_faie_backtest independently on
    each chunk.

    Built specifically to feed certification.self_audit.detect_overfitting,
    which needs >=2 periods' worth of comparable metrics — this is the
    "once §6's backtest harness produces both [in-sample and out-of-sample]"
    case the Self Audit spec section (Phase-2 spec §4) names as its
    prerequisite for overfitting detection.

    Returns: {period_label: {"agreement_rate": ..., "evaluated_rows": ...,
    "opposite_disagreement_rate": ...}}, one entry per period, in order.
    """
    if history_rows is None:
        history_rows = read_csv_records(csv_path or DEFAULT_HISTORY_CSV)

    n_periods = max(2, int(n_periods))
    labels = period_labels or (
        ["in_sample", "out_of_sample"] if n_periods == 2
        else [f"period_{i+1}" for i in range(n_periods)]
    )
    if len(labels) != n_periods:
        labels = [f"period_{i+1}" for i in range(n_periods)]

    total = len(history_rows)
    chunk_size = max(1, total // n_periods) if total else 0
    metrics_by_period: Dict[str, Dict[str, Any]] = {}
    for i, label in enumerate(labels):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < n_periods - 1 else total
        chunk = history_rows[start:end] if total else []
        chunk_report = run_faie_backtest(history_rows=chunk)
        metrics_by_period[label] = {
            "agreement_rate": chunk_report.agreement_rate,
            "evaluated_rows": chunk_report.evaluated_rows,
            "skipped_rows": chunk_report.skipped_rows,
            "opposite_disagreement_rate": (
                chunk_report.opposite_disagreements / chunk_report.evaluated_rows
                if chunk_report.evaluated_rows else 0.0
            ),
        }
    return metrics_by_period
