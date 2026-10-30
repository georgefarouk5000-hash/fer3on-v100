"""Level 2 certification wrapper (200 trades)."""

from certification.framework import evaluate_target


def evaluate_level2(trades: int | None = None, win_rate: float | None = None, profit_factor: float | None = None, drawdown: float | None = None) -> dict:
    level = evaluate_target(200)
    metrics = dict(level.get("metrics", {}))
    if trades is not None:
        level["progress_trades"] = int(trades)
        level["completed"] = int(trades) >= 200
    if win_rate is not None:
        metrics["win_rate"] = float(win_rate)
    if profit_factor is not None:
        metrics["profit_factor"] = float(profit_factor)
    if drawdown is not None:
        metrics["max_drawdown"] = float(drawdown)
    return {
        "level": 2,
        "required_trades": 200,
        "passed": bool(level.get("completed")),
        "status": "ACTIVE",
        **level,
        "metrics": metrics,
    }
