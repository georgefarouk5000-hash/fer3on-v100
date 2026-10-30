# =============================================================================
# FER3ON — Development Readiness Gate
# =============================================================================
# السياق: بعد مراجعة تقرير "Phase X — Cognitive Institutional Layer"
# (يقترح 14 نظامًا معماريًا جديدًا)، كانت التوصية: لا تُضاف أي بنية جديدة
# قبل إثبات أن الأساسيات شغالة فعليًا على بيانات حقيقية. هذه الأداة تحوّل
# تلك التوصية من "كلام" إلى checklist قابل للتشغيل، بمعايير حقيقية مبنية
# على بيانات هذا المشروع تحديدًا:
#
#   Gate 1 — Data Quality: نسبة تغطية enrichment fields (choch/liquidity/
#            mtf/atr) على الصفقات المُغلقة الأخيرة في ai_memory.csv. لولا
#            إصلاح الـ enrichment bug السابق، هذا الـ Gate كان سيفشل دائمًا.
#   Gate 2 — Real Backtest: هل تم تشغيل tools/ci_shadow_backtest_gate.py
#            فعليًا على بيانات حقيقية (--csv)، وليس synthetic فقط؟
#   Gate 3 — Paper/Live Trading Sample: هل يوجد عدد كافٍ من الصفقات
#            المُغلقة الحقيقية عبر مدة كافية؟
#   Gate 4 (استشاري، لا يمنع الجاهزية) — Market Condition Diversity: هل
#            العيّنة تغطي أكثر من نظام سوق واحد (TRENDING/RANGING/...)؟
#            هذا تقريب بسيط لروح Walk-Forward Analysis، وليس بديلاً عنه.
#
# هذه الأداة لا تمنع أي شيء تلقائيًا (ليست CI gate تُفشل بناء) — هي أداة
# قرار بشري: تُشغَّل يدويًا قبل البدء في أي تطوير معماري جديد، وتُعطي
# إجابة واضحة: جاهز أو غير جاهز، ولماذا تحديدًا.
# =============================================================================

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.ai_memory import load_memory_records
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from core.settings import BACKUP_DIR  # noqa: F401  (kept for parity with other tools' import style)

CI_BASELINE_PATH = "data/analytics/ci_shadow_backtest_baseline.json"

_CLOSED_RESULTS = {"WIN", "LOSS", "BREAKEVEN"}
_ENRICHMENT_FIELDS = ["atr", "choch_strength", "liq_map_score", "liq_map_dir", "mtf_structural"]

# Thresholds — deliberately explicit constants (not buried magic numbers)
# so they're easy to review/adjust as the project matures.
ENRICHMENT_COVERAGE_PASS = 0.60
ENRICHMENT_COVERAGE_WARN = 0.30
MIN_CLOSED_TRADES_FOR_ENRICHMENT_CHECK = 5

MIN_TRADES_PASS = 30
MIN_TRADES_WARN = 10
MIN_DAYS_SPAN_PASS = 14
MIN_DAYS_SPAN_WARN = 5


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _closed_trades(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in records if str(r.get("result", "")).upper() in _CLOSED_RESULTS]


def _check_data_quality(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = _closed_trades(records)
    # Most-recent-first by date, best-effort parse (unparseable dates sort last)
    closed_sorted = sorted(closed, key=lambda r: _parse_date(r.get("date", "")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    sample = closed_sorted[:50]  # last 50 closed trades, or fewer

    if len(sample) < MIN_CLOSED_TRADES_FOR_ENRICHMENT_CHECK:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "closed_trades_checked": len(sample),
            "coverage": None,
            "message": f"Only {len(sample)} closed trades — need at least {MIN_CLOSED_TRADES_FOR_ENRICHMENT_CHECK} to measure enrichment coverage meaningfully.",
        }

    populated = 0
    for row in sample:
        fields_ok = sum(1 for f in _ENRICHMENT_FIELDS if str(row.get(f, "")).strip() not in ("", "0", "0.0", "NONE", "UNKNOWN"))
        if fields_ok >= 3:  # majority of the 5 fields present counts as "enriched"
            populated += 1

    coverage = populated / len(sample)
    if coverage >= ENRICHMENT_COVERAGE_PASS:
        status = "PASS"
    elif coverage >= ENRICHMENT_COVERAGE_WARN:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "status": status,
        "closed_trades_checked": len(sample),
        "coverage": round(coverage, 3),
        "message": f"{populated}/{len(sample)} recent closed trades ({coverage:.0%}) have real enrichment data (choch/liquidity/mtf/atr).",
    }


def _check_real_backtest(baseline_path: str = CI_BASELINE_PATH) -> Dict[str, Any]:
    if not os.path.exists(baseline_path):
        return {
            "status": "FAIL",
            "message": f"No {baseline_path} found — the CI shadow backtest gate has never been run. "
                       f"Run: python -m fer3on ci-gate --csv <real_historical_data.csv>",
        }
    try:
        with open(baseline_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as error:
        return {"status": "FAIL", "message": f"{baseline_path} exists but couldn't be read: {error}"}

    csv_source = data.get("csv")
    if not csv_source:
        return {
            "status": "WARN",
            "message": f"{baseline_path} exists but has no real --csv source recorded "
                       f"(bootstrapped from synthetic data — see BACKTEST_VALIDITY_NOTICE.md). "
                       f"Re-run with real historical data to get a meaningful baseline.",
        }
    return {
        "status": "PASS",
        "message": f"Real-data backtest baseline found (expectancy=${data.get('expectancy', '?')}, source={csv_source}).",
    }


def _check_trading_sample(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = _closed_trades(records)
    dates = [d for d in (_parse_date(r.get("date", "")) for r in closed) if d is not None]

    if not dates:
        return {
            "status": "FAIL",
            "trade_count": len(closed),
            "days_span": 0,
            "message": "No closed trades with a parseable date — no paper/live trading sample yet.",
        }

    span_days = (max(dates) - min(dates)).total_seconds() / 86400.0
    count = len(closed)

    count_ok = "PASS" if count >= MIN_TRADES_PASS else "WARN" if count >= MIN_TRADES_WARN else "FAIL"
    span_ok = "PASS" if span_days >= MIN_DAYS_SPAN_PASS else "WARN" if span_days >= MIN_DAYS_SPAN_WARN else "FAIL"

    # Overall status is the worse of the two sub-checks
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    status = min([count_ok, span_ok], key=lambda s: order[s])

    return {
        "status": status,
        "trade_count": count,
        "days_span": round(span_days, 1),
        "message": f"{count} closed trades over {span_days:.1f} days "
                   f"(need >= {MIN_TRADES_PASS} trades over >= {MIN_DAYS_SPAN_PASS} days for PASS).",
    }


def _check_market_diversity(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed = _closed_trades(records)
    regimes = {}
    for r in closed:
        regime = str(r.get("market_regime", "UNKNOWN")).upper()
        if regime and regime != "UNKNOWN":
            regimes[regime] = regimes.get(regime, 0) + 1

    distinct = len(regimes)
    status = "PASS" if distinct >= 2 else "WARN" if distinct == 1 else "INSUFFICIENT_SAMPLE"
    return {
        "status": status,
        "distinct_regimes": distinct,
        "breakdown": regimes,
        "message": f"Closed trades span {distinct} distinct market regime(s): {regimes or '(none recorded)'}.",
    }


def run_readiness_check() -> Dict[str, Any]:
    records = load_memory_records()

    gates = {
        "data_quality": _check_data_quality(records),
        "real_backtest": _check_real_backtest(),
        "trading_sample": _check_trading_sample(records),
        "market_diversity": _check_market_diversity(records),  # advisory only
    }

    # Gate 4 (market_diversity) is advisory and never blocks readiness by
    # itself — everything else genuinely needs to hold before adding new
    # architecture on top of an unvalidated system.
    blocking_gates = {k: v for k, v in gates.items() if k != "market_diversity"}
    blocking_statuses = {v["status"] for v in blocking_gates.values()}

    if blocking_statuses <= {"PASS"}:
        verdict = "READY"
    elif "FAIL" in blocking_statuses:
        verdict = "NOT_READY"
    else:
        verdict = "NOT_READY_YET"  # only WARN/INSUFFICIENT_SAMPLE, no hard FAIL

    return {"verdict": verdict, "gates": gates}


def print_readiness_report() -> str:
    report = run_readiness_check()
    icons = {"PASS": "✅", "WARN": "🟡", "FAIL": "❌", "INSUFFICIENT_SAMPLE": "ℹ️"}

    lines = [
        "=" * 70,
        "DEVELOPMENT READINESS GATE — data quality / real backtest / live sample",
        "=" * 70,
    ]
    for name, gate in report["gates"].items():
        icon = icons.get(gate["status"], "❔")
        label = "market_diversity (advisory)" if name == "market_diversity" else name
        lines.append(f"{icon} {label:<28} [{gate['status']}]")
        lines.append(f"    {gate['message']}")
    lines.append("-" * 70)
    verdict = report["verdict"]
    if verdict == "READY":
        lines.append("✅ VERDICT: READY — the basics check out on real data.")
        lines.append("   Safe to consider new architectural work from here.")
    elif verdict == "NOT_READY_YET":
        lines.append("🟡 VERDICT: NOT READY YET — no hard failures, but at least one")
        lines.append("   gate needs more real data before trusting the results.")
    else:
        lines.append("❌ VERDICT: NOT READY — fix the FAIL gate(s) above before adding")
        lines.append("   any new architecture (Reasoning Engine, Narrative Engine, etc.).")
    lines.append("=" * 70)

    text = "\n".join(lines)
    print(text)
    return text


def main() -> int:
    report = run_readiness_check()
    print_readiness_report()
    return 0 if report["verdict"] == "READY" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
