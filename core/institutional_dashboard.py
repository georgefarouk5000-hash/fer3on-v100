# =========================================
# FER3ON AI V1.5 — INSTITUTIONAL DASHBOARD
# =========================================

import json
import math
import os
from collections import defaultdict
from datetime import date

from brain.trade_dna import rank_strategies
from core.ai_memory import load_memory_records

MEMORY_FILE = "data/memory/ai_memory.csv"
DASHBOARD_FILE = "data/analytics/dashboard_state.json"


def _safe_profit(row):
    try:
        return float(row.get("profit", 0) or 0)
    except Exception:
        return 0.0


def _compute_drawdown(profits):
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 2)


def _compute_sharpe(profits):
    if len(profits) < 2:
        return 0.0
    mean = sum(profits) / len(profits)
    var = sum((p - mean) ** 2 for p in profits) / (len(profits) - 1)
    std = math.sqrt(var)
    return round(mean / std, 3) if std > 0 else 0.0


def _compute_sortino(profits):
    if len(profits) < 2:
        return 0.0
    mean = sum(profits) / len(profits)
    downside = [p for p in profits if p < 0]
    if not downside:
        return 0.0
    var = sum((p - 0) ** 2 for p in downside) / len(downside)
    std = math.sqrt(var)
    return round(mean / std, 3) if std > 0 else 0.0


def _group_pnl(rows, key_prefix_len):
    grouped = defaultdict(float)
    for row in rows:
        stamp = str(row.get("date", row.get("timestamp", "")))
        key = stamp[:key_prefix_len] if stamp else "UNKNOWN"
        grouped[key] += _safe_profit(row)
    return {k: round(v, 2) for k, v in sorted(grouped.items())}


def _compute_calmar(profits, drawdown):
    if not profits:
        return 0.0
    total_return = sum(profits)
    return round(total_return / drawdown, 3) if drawdown > 0 else (float("inf") if total_return > 0 else 0.0)


def _equity_curve(profits):
    equity = 0.0
    curve = []
    for p in profits:
        equity += float(p or 0)
        curve.append(round(equity, 2))
    return curve


def _strategy_stats(rows):
    grouped = defaultdict(lambda: {"wins": 0, "losses": 0, "profit": 0.0, "profits": []})
    for row in rows:
        strat = str(row.get("strategy", "UNKNOWN")).upper()
        profit = _safe_profit(row)
        grouped[strat]["profit"] += profit
        grouped[strat]["profits"].append(profit)
        if str(row.get("result", "")).upper() == "WIN":
            grouped[strat]["wins"] += 1
        else:
            grouped[strat]["losses"] += 1
    out = []
    for strat, data in grouped.items():
        total = data["wins"] + data["losses"]
        out.append({
            "strategy": strat,
            "trades": total,
            "win_rate": round((data["wins"] / total) * 100, 1) if total else 0.0,
            "profit": round(data["profit"], 2),
            "avg_pnl": round(sum(data["profits"]) / total, 2) if total else 0.0,
        })
    out.sort(key=lambda x: (x["profit"], x["win_rate"]), reverse=True)
    return out


def get_overall_stats(days=7):
    rows = load_memory_records()
    if not rows:
        return None
    recent_rows = rows[-200:]
    profits = [_safe_profit(r) for r in recent_rows]
    total = len(recent_rows)
    wins = sum(1 for r in recent_rows if str(r.get("result", "")).upper() == "WIN")
    gross_wins = sum(p for p in profits if p > 0)
    gross_losses = abs(sum(p for p in profits if p < 0))
    avg_win = round(gross_wins / max(1, sum(1 for p in profits if p > 0)), 2)
    avg_loss = round(abs(sum(p for p in profits if p < 0)) / max(1, sum(1 for p in profits if p < 0)), 2)
    expectancy = round(sum(profits) / total, 2) if total else 0.0
    drawdown = _compute_drawdown(profits)
    return {
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "winrate": round(wins / total * 100, 1) if total > 0 else 0,
        "total_profit": round(sum(profits), 2),
        "profit_factor": round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf"),
        "drawdown": drawdown,
        "sharpe_ratio": _compute_sharpe(profits),
        "sortino_ratio": _compute_sortino(profits),
        "calmar_ratio": _compute_calmar(profits, drawdown),
        "equity_curve": _equity_curve(profits),
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "strategy_ranking": _strategy_stats(recent_rows),
    }


def build_v2_dashboard_snapshot(rows=None):
    rows = rows or load_memory_records()
    if not rows:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "drawdown": 0.0,
            "daily_pnl": {},
            "monthly_pnl": {},
            "strategy_ranking": [],
            "equity_curve": [],
        }

    profits = [_safe_profit(r) for r in rows]
    drawdown = _compute_drawdown(profits)
    return {
        "win_rate": round(sum(1 for r in rows if str(r.get("result", "")).upper() == "WIN") / max(1, len(rows)) * 100, 1),
        "profit_factor": round(sum(p for p in profits if p > 0) / max(1.0, abs(sum(p for p in profits if p < 0))), 2),
        "sharpe": _compute_sharpe(profits),
        "sortino": _compute_sortino(profits),
        "calmar": _compute_calmar(profits, drawdown),
        "drawdown": drawdown,
        "daily_pnl": _group_pnl(rows, 10),
        "monthly_pnl": _group_pnl(rows, 7),
        "strategy_ranking": _strategy_stats(rows),
        "equity_curve": _equity_curve(profits),
    }


def build_daily_report():
    today_str = date.today().isoformat()
    rows = load_memory_records()
    today_trades = [r for r in rows if str(r.get("date", "")).startswith(today_str)]
    if not today_trades:
        return _empty_report(today_str)

    profits = [_safe_profit(r) for r in today_trades]
    total = len(today_trades)
    wins = sum(1 for r in today_trades if str(r.get("result", "")).upper() == "WIN")
    losses = total - wins
    winrate = round(wins / total * 100, 1) if total > 0 else 0
    total_profit = round(sum(profits), 2)
    gross_wins = sum(p for p in profits if p > 0)
    gross_losses = abs(sum(p for p in profits if p < 0))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else float("inf")
    drawdown = _compute_drawdown(profits)
    sharpe = _compute_sharpe(profits)
    sortino = _compute_sortino(profits)
    expectancy = round(sum(profits) / total, 2) if total else 0.0
    avg_win = round(gross_wins / max(1, sum(1 for p in profits if p > 0)), 2)
    avg_loss = round(abs(sum(p for p in profits if p < 0)) / max(1, sum(1 for p in profits if p < 0)), 2)

    daily_pnl = _group_pnl(rows, 10)
    monthly_pnl = _group_pnl(rows, 7)
    strategy_ranking = _strategy_stats(today_trades)
    dna_ranking = rank_strategies(min_trades=1)

    dashboard_state = {
        "date": today_str,
        "total": total,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "total_profit": total_profit,
        "profit_factor": profit_factor,
        "max_drawdown": drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": _compute_calmar(profits, drawdown),
        "equity_curve": _equity_curve(profits),
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "daily_pnl": daily_pnl,
        "monthly_pnl": monthly_pnl,
        "strategy_ranking": strategy_ranking,
        "dna_strategy_ranking": dna_ranking,
    }
    _save_dashboard(dashboard_state)

    top_strategy = strategy_ranking[0]["strategy"] if strategy_ranking else "N/A"
    return (
        f"📊 FER3ON AI V1.5 — DAILY REPORT\n"
        f"📅 {today_str}\n"
        f"{'─' * 28}\n"
        f"📈 Trades      : {total} (W:{wins} / L:{losses})\n"
        f"🎯 Win Rate    : {winrate}%\n"
        f"💵 PnL         : {total_profit}$\n"
        f"⚖️ ProfitFactor: {profit_factor}\n"
        f"📉 Drawdown    : {drawdown}$\n"
        f"📐 Sharpe      : {sharpe}\n"
        f"📏 Sortino     : {sortino}\n"
        f"🧮 Expectancy  : {expectancy}$\n"
        f"✅ Avg Win     : {avg_win}$\n"
        f"❌ Avg Loss    : {avg_loss}$\n"
        f"🏆 Top Strategy: {top_strategy}\n"
        f"🤖 FER3ON AI V1.5"
    )


def _empty_report(today_str):
    state = {
        "date": today_str,
        "total": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0,
        "total_profit": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "calmar_ratio": 0.0,
        "equity_curve": [],
        "expectancy": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "daily_pnl": {},
        "monthly_pnl": {},
        "strategy_ranking": [],
        "dna_strategy_ranking": rank_strategies(min_trades=1),
    }
    _save_dashboard(state)
    return (
        f"📊 FER3ON AI V1.5 — DAILY REPORT\n"
        f"📅 {today_str}\n"
        f"{'─' * 28}\n"
        f"📭 No trades today.\n"
        f"🤖 FER3ON AI V1.5"
    )


def _save_dashboard(data):
    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    try:
        with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
