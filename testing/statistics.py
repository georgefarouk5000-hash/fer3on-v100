# =========================================
# FER3ON V5.2 — STATISTICAL ANALYSIS ENGINE
# Profit Factor | Drawdown | Sharpe | Expectancy | Recovery
# =========================================

import math
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    import math as np
    HAS_NUMPY = False
    print("⚠️  numpy not found — install: pip install numpy")

from core.data_integrity import HISTORY_COLUMNS, HISTORY_FILE, read_csv_records


# =========================================
# LOAD TRADES
# =========================================

def load_trades(filepath=None):
    filepath = filepath or HISTORY_FILE
    rows = read_csv_records(filepath)
    trades = []
    for row in rows:
        try:
            p = float(row.get("profit", 0) or 0)
        except Exception:
            p = 0.0
        r = str(row.get("result", "")).upper()
        trades.append({**row, "profit_f": p, "result_clean": r})
    return trades


# =========================================
# FULL STATISTICAL ANALYSIS
# =========================================

def full_stats_analysis(trades=None, risk_free_rate=0.02):
    if trades is None:
        trades = load_trades()
    if not trades:
        return _empty_stats("NO_DATA")

    profits = [t["profit_f"] for t in trades]
    results = [t["result_clean"] for t in trades]
    wins = [p for p, r in zip(profits, results) if r == "WIN" and p >= 0]
    losses = [p for p, r in zip(profits, results) if r == "LOSS" and p < 0]

    total = len(trades)
    n_win = len(wins)
    n_loss = len(losses)
    if total == 0:
        return _empty_stats("EMPTY")

    win_rate = round(n_win / total * 100, 2)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 0.001
    pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else 99.0

    avg_win = round(gross_win / len(wins), 2) if wins else 0
    avg_loss = round(gross_loss / len(losses), 2) if losses else 0
    expect = round((n_win / total) * avg_win - (n_loss / total) * avg_loss, 2) if total > 0 else 0

    equity = [0.0]
    cumul = peak = max_dd = 0.0
    peak_idx = dd_start = 0
    dd_periods = []
    for i, p in enumerate(profits):
        cumul += p
        equity.append(cumul)
        if cumul > peak:
            peak = cumul
            peak_idx = i
        dd = peak - cumul
        if dd > max_dd:
            max_dd = dd
            dd_start = peak_idx
        if dd > 0:
            dd_periods.append(dd)

    max_dd = round(max_dd, 2)
    net_profit = round(cumul, 2)

    if len(profits) > 1:
        ret_mean = np.mean(profits)
        ret_std = np.std(profits, ddof=1)
        if ret_std > 0:
            daily_rf = risk_free_rate / 252
            sharpe = round((ret_mean - daily_rf) / ret_std * math.sqrt(252), 3)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    recovery = round(net_profit / max_dd, 3) if max_dd > 0 else (99.0 if net_profit > 0 else 0)

    down_returns = [p for p in profits if p < 0]
    if down_returns and len(down_returns) > 1:
        down_std = np.std(down_returns, ddof=1)
        sortino = round((np.mean(profits)) / down_std * math.sqrt(252), 3) if down_std > 0 else 0
    else:
        sortino = 0.0

    max_win_streak = max_loss_streak = curr_win = curr_loss = 0
    for r in results:
        if r == "WIN":
            curr_win += 1
            curr_loss = 0
            max_win_streak = max(max_win_streak, curr_win)
        elif r == "LOSS":
            curr_loss += 1
            curr_win = 0
            max_loss_streak = max(max_loss_streak, curr_loss)

    by_strategy = {}
    by_session = {}
    by_regime = {}
    for t in trades:
        for dim, key in [
            (by_strategy, t.get("strategy", "?")),
            (by_session, t.get("session", "?")),
            (by_regime, t.get("market_regime", "?")),
        ]:
            if key not in dim:
                dim[key] = {"wins": 0, "losses": 0, "profit": 0.0}
            if t["result_clean"] == "WIN":
                dim[key]["wins"] += 1
            elif t["result_clean"] == "LOSS":
                dim[key]["losses"] += 1
            dim[key]["profit"] = round(dim[key]["profit"] + t["profit_f"], 2)

    for dim_dict in [by_strategy, by_session, by_regime]:
        for k in dim_dict:
            w = dim_dict[k]["wins"]
            l = dim_dict[k]["losses"]
            dim_dict[k]["winrate"] = round(w / (w + l) * 100, 1) if (w + l) > 0 else 0

    if pf >= 2.0 and sharpe >= 1.0 and win_rate >= 55:
        grade = "INSTITUTIONAL ✨"
    elif pf >= 1.5 and win_rate >= 50:
        grade = "GOOD 👍"
    elif pf >= 1.2:
        grade = "ACCEPTABLE ✅"
    elif pf < 1.0:
        grade = "LOSING ❌"
    else:
        grade = "MARGINAL ⚠️"

    return {
        "total_trades": total,
        "n_wins": n_win,
        "n_losses": n_loss,
        "win_rate": win_rate,
        "net_profit": net_profit,
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "expectancy": expect,
        "recovery_factor": recovery,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "by_strategy": by_strategy,
        "by_session": by_session,
        "by_regime": by_regime,
        "grade": grade,
        "equity_curve": equity,
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
    }


def _empty_stats(reason):
    return {
        "total_trades": 0, "n_wins": 0, "n_losses": 0, "win_rate": 0,
        "net_profit": 0, "profit_factor": 0, "max_drawdown": 0,
        "sharpe_ratio": 0, "sortino_ratio": 0, "expectancy": 0,
        "recovery_factor": 0, "avg_win": 0, "avg_loss": 0,
        "max_win_streak": 0, "max_loss_streak": 0,
        "by_strategy": {}, "by_session": {}, "by_regime": {},
        "grade": "N/A", "equity_curve": [], "gross_win": 0, "gross_loss": 0,
        "error": reason,
    }


def format_stats_report(stats):
    if "error" in stats:
        return f"📊 Stats: {stats['error']}"

    lines = [
        f"📊 PERFORMANCE REPORT",
        f"{'=' * 40}",
        f"Trades:    {stats['total_trades']} ({stats['n_wins']}W / {stats['n_losses']}L)",
        f"Win Rate:  {stats['win_rate']}%",
        f"Net P/L:   ${stats['net_profit']:+.2f}",
        f"{'—' * 40}",
        f"Profit Factor:   {stats['profit_factor']:.3f}",
        f"Max Drawdown:    ${stats['max_drawdown']:.2f}",
        f"Sharpe Ratio:    {stats['sharpe_ratio']:.3f}",
        f"Sortino Ratio:   {stats['sortino_ratio']:.3f}",
        f"Expectancy:      ${stats['expectancy']:+.2f}",
        f"Recovery Factor: {stats['recovery_factor']:.3f}",
        f"{'—' * 40}",
        f"Avg Win:  ${stats['avg_win']:.2f}",
        f"Avg Loss: ${stats['avg_loss']:.2f}",
        f"Max Win Streak:  {stats['max_win_streak']}",
        f"Max Loss Streak: {stats['max_loss_streak']}",
        f"{'—' * 40}",
        f"Grade:  {stats['grade']}",
    ]

    if stats.get("by_strategy"):
        lines.append("By Strategy:")
        for strat, d in stats["by_strategy"].items():
            lines.append(f"  {strat}: WR={d['winrate']}% P/L=${d['profit']:+.2f}")

    return "\n".join(lines)
