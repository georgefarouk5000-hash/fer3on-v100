import os
from typing import Dict, Any

from core.data_integrity import HISTORY_COLUMNS, HISTORY_FILE, read_csv_records
from core.settings import ANALYTICS_DIR, BUILD_ID


def analyze_trades():
    raw_trades = read_csv_records(HISTORY_FILE, HISTORY_COLUMNS)
    trades = [
        row for row in raw_trades
        if str(row.get("build_id", "") or "").strip() == str(BUILD_ID)
    ]
    if not trades:
        return "📈 No trades recorded yet"

    profits = []
    results = []
    wins = losses = 0

    for row in trades:
        try:
            p = float(row.get("profit", 0) or 0)
        except Exception:
            p = 0.0
        r = str(row.get("result", "")).upper()
        profits.append(p)
        results.append(r)
        if r == "WIN":
            wins += 1
        elif r == "LOSS":
            losses += 1

    total = wins + losses
    if total == 0:
        return "📈 No closed trades yet"

    winrate = round(wins / total * 100, 1)
    total_profit = round(sum(profits), 2)

    peak = equity = max_dd = 0
    for p in profits:
        equity += p
        if equity > peak:
            peak = equity
        max_dd = max(max_dd, peak - equity)
    max_dd = round(max_dd, 2)

    gross_win = sum(p for p in profits if p > 0)
    gross_loss = abs(sum(p for p in profits if p < 0))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 0

    win_profits = [p for p in profits if p > 0]
    loss_profits = [p for p in profits if p < 0]
    avg_win = round(sum(win_profits) / len(win_profits), 2) if win_profits else 0
    avg_loss = round(sum(loss_profits) / len(loss_profits), 2) if loss_profits else 0
    best = round(max(profits), 2) if profits else 0
    worst = round(min(profits), 2) if profits else 0

    streak = 0
    streak_type = ""
    for r in reversed(results):
        if streak == 0:
            streak_type = r
            streak = 1
        elif r == streak_type:
            streak += 1
        else:
            break

    streak_str = f"{streak}W" if streak_type == "WIN" else f"{streak}L" if streak_type == "LOSS" else "-"

    metrics = {
        "total_trades": total,
        "winrate": round(winrate, 1),
        "total_profit": round(total_profit, 2),
        "profit_factor": round(pf, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": round(best, 2),
        "worst_trade": round(worst, 2),
        "streak": streak_str,
    }

    return (
        f"📈 ANALYTICS | {total}T"
        f" WR:{winrate}%"
        f" P:{total_profit}$"
        f" PF:{pf}"
        f" DD:{max_dd}$"
        f" AvgW:{avg_win}$"
        f" AvgL:{avg_loss}$"
        f" Best:{best}$"
        f" Worst:{worst}$"
        f" Streak:{streak_str}"
    ), metrics


def write_daily_performance_report(metrics: Dict[str, Any] | None = None, output_path: str | None = None) -> Dict[str, Any]:
    """Write a markdown report with daily performance metrics."""
    if metrics is None:
        _, metrics = analyze_trades()

    path = output_path or os.path.join(ANALYTICS_DIR, "daily_performance_report.md")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    content = [
        "# DAILY PERFORMANCE REPORT",
        "",
        f"- Total Trades: {metrics.get('total_trades', 0)}",
        f"- Win Rate: {metrics.get('winrate', 0)}%",
        f"- Total Profit: {metrics.get('total_profit', 0)}",
        f"- Profit Factor: {metrics.get('profit_factor', 0)}",
        f"- Max Drawdown: {metrics.get('max_drawdown', 0)}",
        f"- Avg Win: {metrics.get('avg_win', 0)}",
        f"- Avg Loss: {metrics.get('avg_loss', 0)}",
        f"- Best Trade: {metrics.get('best_trade', 0)}",
        f"- Worst Trade: {metrics.get('worst_trade', 0)}",
        f"- Streak: {metrics.get('streak', '-')}",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")
    return {"report_file": path, "metrics": metrics}
