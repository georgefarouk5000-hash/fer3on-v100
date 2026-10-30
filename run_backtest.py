#!/usr/bin/env python3
# =========================================
# FER3ON V5.7 — BACKTEST RUNNER
# يُشغَّل منفصلاً لاختبار الاستراتيجية
# Usage: python run_backtest.py [--bars 5000] [--balance 10000]
# =========================================

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.mt5_compat import mt5, MT5_AVAILABLE

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv("config.env")

from testing.backtester import run_full_test_suite, run_backtest, walk_forward_test, monte_carlo_test
from testing.statistics import full_stats_analysis, format_stats_report
from core.settings import SYMBOL


def _build_synthetic_rates(n_bars):
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


def _load_rates_from_csv(csv_path):
    """
    يحمّل بيانات تاريخية حقيقية من ملف CSV (مُصدَّر من MT5/أي منصة).
    الأعمدة المتوقعة: open, high, low, close (وأعمدة إضافية تُتجاهل).
    هذا هو المسار الموصى به لتوليد أدلة جدوى فعلية (نقطة الضعف #2:
    لا تُصدّق أي إشارة يولّدها البوت بلا تحقق على بيانات تاريخية حقيقية).
    """
    import csv as csv_module

    rates = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        required = ["open", "high", "low", "close"]
        missing = [c for c in required if c not in cols]
        if missing:
            raise ValueError(
                f"ملف CSV ينقصه الأعمدة المطلوبة: {missing} — الأعمدة الموجودة: {reader.fieldnames}"
            )
        for row in reader:
            rates.append({
                "open": float(row[cols["open"]]),
                "high": float(row[cols["high"]]),
                "low": float(row[cols["low"]]),
                "close": float(row[cols["close"]]),
                "tick_volume": float(row.get(cols.get("volume", ""), 100) or 100),
            })

    if not rates:
        raise ValueError(f"لم يتم تحميل أي شموع من {csv_path}")

    print(f"✅ Loaded {len(rates)} REAL historical bars from CSV: {csv_path}")
    return rates


def _load_rates(args):
    if getattr(args, "csv", None):
        return _load_rates_from_csv(args.csv), True, "real_csv"

    if not MT5_AVAILABLE:
        print("⚠️ MetaTrader5 package not installed — running synthetic demo backtest")
        print("⚠️ WARNING: نتائج هذا التشغيل SYNTHETIC (عشوائية) ولا تثبت أي جدوى حقيقية")
        print("⚠️ للحصول على تحقق فعلي استخدم --csv <path> ببيانات تاريخية حقيقية")
        return _build_synthetic_rates(args.bars), False, "synthetic"

    if not mt5.initialize():
        print(f"❌ MT5 init failed: {mt5.last_error()}")
        print("⚠️ Running in DEMO mode with synthetic data...")
        print("⚠️ WARNING: نتائج هذا التشغيل SYNTHETIC (عشوائية) ولا تثبت أي جدوى حقيقية")
        return _build_synthetic_rates(args.bars), False, "synthetic"

    tf_map = {
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(args.tf.upper(), mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, args.bars)
    if rates is None:
        print(f"❌ Cannot fetch rates for {SYMBOL}")
        mt5.shutdown()
        sys.exit(1)

    print(f"✅ Loaded {len(rates)} bars | {SYMBOL} | {args.tf}")
    return rates, True, "real_mt5"


def main():
    parser = argparse.ArgumentParser(description="FER3ON V5.7 Backtest Runner")
    parser.add_argument("--bars", type=int, default=5000, help="عدد الشموع (default: 5000)")
    parser.add_argument("--balance", type=float, default=10000, help="الرصيد الابتدائي (default: 10000)")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk percentage")
    parser.add_argument("--tf", type=str, default="H1", help="الإطار الزمني: M5 M15 H1 H4 D1")
    parser.add_argument("--mode", type=str, default="full", help="full | wf | mc | stats")
    parser.add_argument("--wf-windows", type=int, default=5, help="عدد نوافذ Walk-Forward")
    parser.add_argument("--mc-sims", type=int, default=1000, help="عدد محاكاة Monte Carlo")
    parser.add_argument("--csv", type=str, default=None, help="مسار CSV ببيانات تاريخية حقيقية (open,high,low,close)")
    args = parser.parse_args()

    rates, mt5_ready, data_source = _load_rates(args)

    print(f"\n{'=' * 55}")
    print("  FER3ON V5.7 BACKTEST ENGINE")
    print(f"  Symbol:      {SYMBOL}")
    print(f"  Bars:        {len(rates)}")
    print(f"  Balance:     ${args.balance:,.0f}")
    print(f"  Risk:        {args.risk}%")
    print(f"  Mode:        {args.mode.upper()}")
    print(f"  Data source: {data_source.upper()}"
          + ("  ⚠️ SYNTHETIC — لا يثبت جدوى حقيقية" if data_source == "synthetic" else "  ✅ بيانات حقيقية"))
    print(f"{'=' * 55}\n")

    if args.mode == "full":
        report = run_full_test_suite(rates, SYMBOL, args.balance)
        _print_full_report(report)
    elif args.mode == "wf":
        result = walk_forward_test(
            rates,
            n_windows=args.wf_windows,
            initial_balance=args.balance,
            risk_pct=args.risk,
        )
        _print_wf_report(result)
    elif args.mode == "mc":
        bt_stats, bt_trades = run_backtest(rates, SYMBOL, args.balance, args.risk)
        profits = [t["profit"] for t in bt_trades]
        result = monte_carlo_test(profits, n_simulations=args.mc_sims, initial_balance=args.balance)
        _print_mc_report(result)
    elif args.mode == "stats":
        stats = full_stats_analysis()
        print(format_stats_report(stats))
    else:
        print(f"❌ Unknown mode: {args.mode}")
        sys.exit(1)

    if mt5_ready and mt5 and mt5.terminal_info():
        mt5.shutdown()


def _print_full_report(r):
    bt = r.get("backtest", {})
    wf = r.get("walk_forward", {})
    mc = r.get("monte_carlo", {})

    print(f"\n{'=' * 55}")
    print("  📊 FULL BACKTEST RESULTS")
    print(f"{'=' * 55}")
    print(f"  Trades:       {bt.get('total_trades', 0)}")
    print(f"  Win Rate:     {bt.get('win_rate', 0)}%")
    print(f"  Net Profit:   ${bt.get('net_profit', 0):+,.2f}  ({bt.get('net_profit_pct', 0):+.2f}%)")
    print(f"  Profit Factor:{bt.get('profit_factor', 0):.3f}")
    print(f"  Max Drawdown: ${bt.get('max_drawdown', 0):,.2f}  ({bt.get('max_dd_pct', 0):.1f}%)")
    print(f"  Sharpe Ratio: {bt.get('sharpe_ratio', 0):.3f}")
    print(f"  Expectancy:   ${bt.get('expectancy', 0):+.2f}")
    print(f"  Recovery Fac: {bt.get('recovery_factor', 0):.3f}")
    print(f"  Avg RR:       {bt.get('avg_rr', 0):.2f}")

    print(f"\n  Walk-Forward: Consistency={wf.get('consistency_pct', 0)}%")
    wf_c = wf.get("combined", {})
    print(f"  WF-Combined:  PF={wf_c.get('profit_factor', 0):.3f}  WR={wf_c.get('win_rate', 0)}%")

    print(f"\n  Monte Carlo ({mc.get('n_simulations', 0)} sims):")
    print(f"  Median Balance: ${mc.get('median_balance', 0):,.0f}")
    print(f"  Worst (5th pct):${mc.get('worst_balance', 0):,.0f}")
    print(f"  Worst Drawdown: ${mc.get('p95_drawdown', 0):,.0f}")
    print(f"  Ruin Probability: {mc.get('ruin_probability', 0)}%")
    print(f"  Grade:          {mc.get('grade', 'N/A')}")
    print(f"{'=' * 55}\n")


def _print_wf_report(r):
    print(f"\n{'=' * 55}")
    print("  📊 WALK-FORWARD RESULTS")
    print(f"{'=' * 55}")
    print(f"  Windows:     {r.get('n_windows', 0)}")
    print(f"  Profitable:  {r.get('profitable_windows', 0)}/{r.get('total_windows', 0)}")
    print(f"  Consistency: {r.get('consistency_pct', 0)}%")
    for i, w in enumerate(r.get("window_results", [])):
        print(f"  Window {i + 1}: WR={w.get('win_rate', 0)}% PF={w.get('profit_factor', 0):.2f} Net=${w.get('net_profit', 0):+,.0f}")
    c = r.get("combined", {})
    print(f"\n  Combined:    WR={c.get('win_rate', 0)}% PF={c.get('profit_factor', 0):.3f} Net=${c.get('net_profit', 0):+,.0f}")
    print(f"{'=' * 55}\n")


def _print_mc_report(r):
    print(f"\n{'=' * 55}")
    print(f"  🎲 MONTE CARLO RESULTS ({r.get('n_simulations', 0)} simulations)")
    print(f"{'=' * 55}")
    print(f"  Initial Balance: ${r.get('initial_balance', 0):,.0f}")
    print(f"  Median Balance:  ${r.get('median_balance', 0):,.0f}")
    print(f"  Best (95th):     ${r.get('best_balance', 0):,.0f}")
    print(f"  Worst (5th):     ${r.get('worst_balance', 0):,.0f}")
    print(f"  Worst Drawdown:  ${r.get('p95_drawdown', 0):,.0f}")
    print(f"  Max DD Ever:     ${r.get('max_drawdown_ever', 0):,.0f}")
    print(f"  Ruin Prob:       {r.get('ruin_probability', 0)}%")
    print(f"  Grade:           {r.get('grade', 'N/A')}")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
