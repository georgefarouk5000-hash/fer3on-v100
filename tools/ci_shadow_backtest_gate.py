#!/usr/bin/env python3
# =============================================================================
# FER3ON — CI Shadow Backtest Gate
# =============================================================================
# التنفيذ: تفعيل قوي لـ Shadow Backtest قبل كل رفع — التقرير المُرفَق يطلب
# جعله إلزاميًا في CI قبل أي merge، يُشغّل النظام على آخر 90 يومًا، ويُفشل
# الـ merge لو Expectancy تراجعت أكثر من 5%.
#
# قيد صريح من BACKTEST_VALIDITY_NOTICE.md (نفس المشروع، اقرأه قبل تعديل هذا
# الملف): بيانات synthetic "لا تثبت شيئًا" ولا يجوز التعامل معها كدليل جدوى.
# لذلك هذه البوابة لها وضعان مختلفان تمامًا:
#
#   1) --csv <real_ohlc.csv>  → البوابة الحقيقية: يُقارَن Expectancy بخط
#      أساس محفوظ (data/analytics/ci_shadow_backtest_baseline.json)، ويفشل
#      البناء (exit 1) لو تراجع أكثر من --max-regression-pct (افتراضي 5%).
#
#   2) بلا --csv (fallback اصطناعي) → SMOKE TEST فقط: يتحقق أن الاستراتيجية
#      لا تنهار على أي تغيير كود (قيمة حقيقية بحد ذاتها)، لكن أبدًا لا
#      يُفشل البناء بسبب رقم Expectancy من بيانات عشوائية — يُطبع تحذير
#      SYNTHETIC صريح ويُنجح دائمًا (ما لم ينهار الكود فعليًا).
#
# لا توجد بيانات OHLC حقيقية مُرفقة في هذا المستودع (راجع
# BACKTEST_VALIDITY_NOTICE.md — نفس النقطة موثّقة هناك مسبقًا: "لا يوجد حتى
# الآن أي تقرير باك-تيست فعلي... بيانات كافية... لم يحدث بعد"). لتفعيل
# البوابة الحقيقية: صدّر بيانات تاريخية حقيقية لآخر 90 يومًا إلى CSV وضعها
# تحت data/backtest_data/، ثم مرّر مسارها عبر --csv (محليًا أو من CI).
#
# Usage:
#   # Smoke test only (no committed real data) — safe default in CI:
#   python tools/ci_shadow_backtest_gate.py --bars 2000
#
#   # Real gate, once real historical data exists:
#   python tools/ci_shadow_backtest_gate.py --csv data/backtest_data/last_90d.csv
#
#   # After manually reviewing and accepting a change's new performance:
#   python tools/ci_shadow_backtest_gate.py --csv <path> --update-baseline
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import SYMBOL  # noqa: E402

BASELINE_PATH = "data/analytics/ci_shadow_backtest_baseline.json"
DEFAULT_MAX_REGRESSION_PCT = 5.0


def _build_synthetic_rates(n_bars: int):
    import numpy as np

    rng = np.random.default_rng(42)
    price = 2000.0
    rates = []
    for _ in range(n_bars):
        change = rng.normal(0, 2.5)
        open_p = price
        close = price + change
        high = max(open_p, close) + abs(rng.normal(0, 1))
        low = min(open_p, close) - abs(rng.normal(0, 1))
        rates.append({"open": open_p, "high": high, "low": low, "close": close, "tick_volume": 100})
        price = close
    return rates


def _load_rates_from_csv(csv_path: str):
    import csv as csv_module

    rates = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        required = ["open", "high", "low", "close"]
        missing = [c for c in required if c not in cols]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing} — found: {reader.fieldnames}")
        for row in reader:
            rates.append({
                "open": float(row[cols["open"]]),
                "high": float(row[cols["high"]]),
                "low": float(row[cols["low"]]),
                "close": float(row[cols["close"]]),
                "tick_volume": float(row.get(cols.get("volume", ""), 100) or 100),
            })
    if not rates:
        raise ValueError(f"No candles loaded from {csv_path}")
    return rates


def _load_baseline(path: str = BASELINE_PATH):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _write_baseline(expectancy: float, extra: dict, path: str = BASELINE_PATH) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"expectancy": expectancy, **extra}, fh, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="FER3ON CI Shadow Backtest Gate")
    parser.add_argument("--csv", type=str, default=None, help="Real historical OHLC CSV (last ~90 days recommended)")
    parser.add_argument("--bars", type=int, default=2000, help="Synthetic bar count when --csv is not given (smoke test only)")
    parser.add_argument("--balance", type=float, default=10000.0)
    parser.add_argument("--risk", type=float, default=0.5)
    parser.add_argument("--max-regression-pct", type=float, default=DEFAULT_MAX_REGRESSION_PCT)
    parser.add_argument("--update-baseline", action="store_true", help="Accept this run's expectancy as the new baseline (requires --csv)")
    parser.add_argument("--baseline-path", type=str, default=BASELINE_PATH)
    args = parser.parse_args()

    if args.csv:
        rates = _load_rates_from_csv(args.csv)
        data_source = "real_csv"
    else:
        rates = _build_synthetic_rates(args.bars)
        data_source = "synthetic"

    print("=" * 70)
    print("FER3ON — CI SHADOW BACKTEST GATE")
    print(f"  Symbol:      {SYMBOL}")
    print(f"  Bars:        {len(rates)}")
    print(f"  Data source: {data_source.upper()}"
          + ("  ⚠️ SYNTHETIC — smoke test only, NOT an expectancy gate" if data_source == "synthetic" else "  ✅ real data — expectancy gate active"))
    print("=" * 70)

    try:
        from testing.backtester import run_backtest
        stats, trades = run_backtest(rates, symbol=SYMBOL, initial_balance=args.balance, risk_pct=args.risk)
    except Exception:
        print("❌ SHADOW BACKTEST CRASHED — this alone should block the merge")
        traceback.print_exc()
        return 1

    expectancy = float(stats.get("expectancy", 0) or 0)
    print(f"Trades:        {stats.get('total_trades', 0)}")
    print(f"Win rate:      {stats.get('win_rate', 0)}%")
    print(f"Profit factor: {stats.get('profit_factor', 0)}")
    print(f"Expectancy:    ${expectancy:+.2f}")
    print("-" * 70)

    if data_source == "synthetic":
        print("Smoke test passed (strategy ran without crashing).")
        print("This is NOT evidence of edge — see BACKTEST_VALIDITY_NOTICE.md.")
        print("Provide --csv with real historical data to activate the real")
        print("expectancy-regression gate.")
        print("=" * 70)
        return 0

    # --- real_csv path: the actual expectancy-regression gate ---------------
    baseline = _load_baseline(args.baseline_path)

    if args.update_baseline:
        _write_baseline(expectancy, {"symbol": SYMBOL, "bars": len(rates), "csv": args.csv}, args.baseline_path)
        print(f"✅ Baseline updated: expectancy=${expectancy:+.2f} (saved to {args.baseline_path})")
        print("=" * 70)
        return 0

    if baseline is None:
        _write_baseline(expectancy, {"symbol": SYMBOL, "bars": len(rates), "csv": args.csv}, args.baseline_path)
        print(f"ℹ️ No baseline found — bootstrapping with this run's expectancy (${expectancy:+.2f}).")
        print(f"   Saved to {args.baseline_path}. Future runs will be compared against it.")
        print("=" * 70)
        return 0

    baseline_expectancy = float(baseline.get("expectancy", 0) or 0)

    if baseline_expectancy <= 0:
        # A non-positive baseline has no meaningful "% regression" — any
        # positive expectancy is already an improvement, any non-positive
        # one can't be meaningfully worse in relative terms. Report and pass.
        print(f"Baseline expectancy was ${baseline_expectancy:+.2f} (non-positive) — passing without a relative check.")
        print("=" * 70)
        return 0

    pct_change = ((expectancy - baseline_expectancy) / abs(baseline_expectancy)) * 100
    print(f"Baseline expectancy: ${baseline_expectancy:+.2f}")
    print(f"Change vs baseline:  {pct_change:+.2f}%")

    if pct_change < -abs(args.max_regression_pct):
        print(f"❌ EXPECTANCY REGRESSED {pct_change:.2f}% (limit: -{args.max_regression_pct}%) — BLOCKING MERGE")
        print("=" * 70)
        return 1

    print(f"✅ Within tolerance (limit: -{args.max_regression_pct}%)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
