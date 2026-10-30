from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from core.data_integrity import HISTORY_COLUMNS, HISTORY_FILE, read_csv_records
from core.settings import BUILD_ID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATUS_JSON = PROJECT_ROOT / "data" / "analytics" / "certification_status.json"
STATUS_MD = PROJECT_ROOT / "certification_status.md"
FRAMEWORK_MD = PROJECT_ROOT / "certification_framework.md"

TARGETS = (
    {"name": "100 Trade Certification", "required_trades": 100},
    {"name": "200 Trade Certification", "required_trades": 200},
)


def _closed_rows() -> List[Dict[str, Any]]:
    # DATA-INTEGRITY FIX: this used to count every row in trades.csv with
    # result WIN/LOSS/BREAKEVEN regardless of which build produced it —
    # certification_status.md was reporting "77 closed trades, WR 54.55%"
    # blending three retired pre-merge strategy versions and one untagged
    # data-merge artifact (57 rows with blank ticket/strategy) together with
    # this build's actual 20 real trades. See core/settings.py BUILD_ID for
    # the full explanation. Certification progress must only ever measure
    # THIS build's real performance, so it's filtered to build_id ==
    # BUILD_ID (rows without a build_id at all — i.e. every pre-existing
    # row before this fix shipped — are legacy by definition and excluded
    # unless explicitly backfilled as such via tools/backfill_build_id.py).
    rows = read_csv_records(HISTORY_FILE, HISTORY_COLUMNS)
    return [
        row for row in rows
        if str(row.get("result", "")).upper() in {"WIN", "LOSS", "BREAKEVEN"}
        and str(row.get("build_id", "")) == BUILD_ID
    ]


def _is_bot_row(row: Dict[str, Any]) -> bool:
    """True for rows produced by the bot's own automated strategies (SMC,
    MICRO, ...). False for MANUAL rows -- trades جو places directly from
    the MT5 terminal alongside the bot, on the same account. Manual trades
    still count toward the account-wide totals (see account_metrics below)
    but must not be mixed into the bot's own certification/performance
    numbers, since they weren't produced by the algorithm being certified
    -- and they don't share its risk controls (no MAX_SL_DISTANCE_DOLLARS
    cap, no per-strategy quality gates), so blending them in would make the
    bot's own numbers look better or worse than what it's actually doing.

    Deliberately a MANUAL denylist, not a strategy allowlist: mt5_history_sync
    resolves each closed deal's strategy from its magic number (see
    core/trade_identity.resolve_trade_identity and the magic map in
    core/trade_identity.STRATEGY_TO_MAGIC), with a fallback that recovers a
    deal's strategy from its parent position when the magic itself is
    missing/unresolvable (core/mt5_history_sync.py). Only a deal that fails
    BOTH of those falls through to MANUAL. So any row that isn't explicitly
    MANUAL was attributed to one of the bot's own strategies -- current ones
    (SMC, MICRO, SCALP, SWING, DAILY, RECOVERY, SURVIVAL) and any added
    later, without needing this file edited every time a new strategy ships.
    An allowlist here would duplicate that resolution with its own
    separately-maintained list, which is exactly what silently miscounted
    RECOVERY/SURVIVAL rows as manual before this fix.

    AUDIT NOTE: this resolution is only as complete as
    core.trade_identity.STRATEGY_TO_MAGIC -- a strategy that opens live
    trades without a registered magic number there will still fall through
    to MANUAL here, same as before. RECOVERY and SURVIVAL now have
    registered magic numbers (core/settings.py RECOVERY_MAGIC/SURVIVAL_MAGIC,
    added because neither had one despite being referenced throughout
    core/recovery_engine.py, core/survival_intelligence.py and others), so
    this file's claim is accurate as of this build -- but it depends on that
    registration being kept up to date, not on something this function can
    verify for itself."""
    return str(row.get("strategy", "") or "").strip().upper() != "MANUAL"


def _profit(row: Dict[str, Any]) -> float:
    try:
        return float(row.get("profit", 0) or 0)
    except Exception:
        return 0.0


def _drawdown(profits: List[float]) -> float:
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 2)


def _sharpe(profits: List[float]) -> float:
    if len(profits) < 2:
        return 0.0
    mean = sum(profits) / len(profits)
    variance = sum((p - mean) ** 2 for p in profits) / (len(profits) - 1)
    std = math.sqrt(variance)
    return round(mean / std, 3) if std > 0 else 0.0


def _recovery_factor(total_profit: float, max_drawdown: float) -> float:
    if max_drawdown <= 0:
        return round(total_profit, 3) if total_profit > 0 else 0.0
    return round(total_profit / max_drawdown, 3)


def _metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    profits = [_profit(row) for row in rows]
    total = len(profits)
    wins = sum(1 for row in rows if str(row.get("result", "")).upper() == "WIN")
    gross_profit = sum(p for p in profits if p > 0)
    gross_loss = abs(sum(p for p in profits if p < 0))
    total_profit = round(sum(profits), 2)
    max_dd = _drawdown(profits)
    expectancy = round(total_profit / total, 3) if total else 0.0
    return {
        "total_trades": total,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss > 0 else (round(gross_profit, 3) if gross_profit > 0 else 0.0),
        "max_drawdown": max_dd,
        "expectancy": expectancy,
        "recovery_factor": _recovery_factor(total_profit, max_dd),
        "sharpe_ratio": _sharpe(profits),
        "net_profit": total_profit,
    }


def build_certification_snapshot() -> Dict[str, Any]:
    rows = _closed_rows()
    bot_rows = [row for row in rows if _is_bot_row(row)]
    manual_rows = [row for row in rows if not _is_bot_row(row)]

    account_metrics = _metrics(rows)
    bot_metrics = _metrics(bot_rows)
    manual_metrics = _metrics(manual_rows)

    levels = []
    for target in TARGETS:
        required = target["required_trades"]
        sample = bot_rows[:required]
        progress = min(len(bot_rows), required)
        pct = round((progress / required) * 100, 2) if required else 0.0
        levels.append(
            {
                "name": target["name"],
                "required_trades": required,
                "progress_trades": progress,
                "progress_pct": pct,
                "completed": len(bot_rows) >= required,
                "metrics": _metrics(sample),
            }
        )

    return {
        "tracked_metrics": [
            "Win Rate",
            "Profit Factor",
            "Max Drawdown",
            "Expectancy",
            "Recovery Factor",
            "Sharpe Ratio",
        ],
        "closed_trade_count": len(rows),
        "bot_trade_count": len(bot_rows),
        "manual_trade_count": len(manual_rows),
        "overall_metrics": account_metrics,
        "account_metrics": account_metrics,
        "bot_metrics": bot_metrics,
        "manual_metrics": manual_metrics,
        "levels": levels,
        "source_file": HISTORY_FILE,
    }


def build_framework_markdown() -> str:
    return "\n".join(
        [
            "# Certification Framework",
            "",
            "## Scope",
            "",
            "- Source of truth: `data/history/trades.csv` closed trades only.",
            "- Update trigger: every MT5 closed-trade sync cycle.",
            "- No new decision architecture added; this framework only measures live FER3ON V2.2 outcomes.",
            "",
            "## Certification levels",
            "",
            "- 100 Trade Certification — progress auto-updates after every closed trade.",
            "- 200 Trade Certification — progress auto-updates after every closed trade.",
            "",
            "## Tracked metrics",
            "",
            "- Win Rate",
            "- Profit Factor",
            "- Max Drawdown",
            "- Expectancy",
            "- Recovery Factor",
            "- Sharpe Ratio",
            "",
            "## Runtime behavior",
            "",
            "- Closed deals enter `data/history/trades.csv` through `core/mt5_history_sync.py`.",
            "- After every sync batch, certification snapshot is recalculated and written to JSON + Markdown outputs.",
            "- Reports do not modify execution decisions; they provide readiness and milestone visibility only.",
            "",
        ]
    ) + "\n"


def build_status_markdown(snapshot: Dict[str, Any] | None = None) -> str:
    snapshot = snapshot or build_certification_snapshot()
    summary = [
        "# Certification Status",
        "",
        f"- Total closed trades: **{snapshot['closed_trade_count']}**",
        f"- Bot trades: **{snapshot['bot_trade_count']}**",
        f"- Manual trades: **{snapshot['manual_trade_count']}**",
        "",
        "## Bot performance",
        "",
        f"- Win Rate: **{snapshot['bot_metrics']['win_rate']}%**",
        f"- Profit Factor: **{snapshot['bot_metrics']['profit_factor']}**",
        f"- Max Drawdown: **{snapshot['bot_metrics']['max_drawdown']}**",
        f"- Expectancy: **{snapshot['bot_metrics']['expectancy']}**",
        f"- Recovery Factor: **{snapshot['bot_metrics']['recovery_factor']}**",
        f"- Sharpe Ratio: **{snapshot['bot_metrics']['sharpe_ratio']}**",
        f"- Net Profit: **{snapshot['bot_metrics']['net_profit']}**",
        "",
        "## Account total",
        "",
        f"- Win Rate: **{snapshot['account_metrics']['win_rate']}%**",
        f"- Profit Factor: **{snapshot['account_metrics']['profit_factor']}**",
        f"- Max Drawdown: **{snapshot['account_metrics']['max_drawdown']}**",
        f"- Expectancy: **{snapshot['account_metrics']['expectancy']}**",
        f"- Recovery Factor: **{snapshot['account_metrics']['recovery_factor']}**",
        f"- Sharpe Ratio: **{snapshot['account_metrics']['sharpe_ratio']}**",
        f"- Net Profit: **{snapshot['account_metrics']['net_profit']}**",
        "",
    ]

    if snapshot.get("manual_trade_count", 0) > 0:
        summary.extend([
            "## Your manual trades only",
            "",
            f"- Win Rate: **{snapshot['manual_metrics']['win_rate']}%**",
            f"- Profit Factor: **{snapshot['manual_metrics']['profit_factor']}**",
            f"- Max Drawdown: **{snapshot['manual_metrics']['max_drawdown']}**",
            f"- Expectancy: **{snapshot['manual_metrics']['expectancy']}**",
            f"- Recovery Factor: **{snapshot['manual_metrics']['recovery_factor']}**",
            f"- Sharpe Ratio: **{snapshot['manual_metrics']['sharpe_ratio']}**",
            f"- Net Profit: **{snapshot['manual_metrics']['net_profit']}**",
            "",
        ])

    summary.extend(["## Levels",
        "",
        "> Certification progress is calculated from bot trades only; manual trades do not count toward the bot certification milestones.",
        "",
    ])

    for level in snapshot["levels"]:
        metrics = level["metrics"]
        summary.extend(
            [
                f"### {level['name']}",
                "",
                f"- Progress: **{level['progress_trades']} / {level['required_trades']}** ({level['progress_pct']}%)",
                f"- Completed: **{'YES' if level['completed'] else 'NO'}**",
                f"- Win Rate: **{metrics['win_rate']}%**",
                f"- Profit Factor: **{metrics['profit_factor']}**",
                f"- Max Drawdown: **{metrics['max_drawdown']}**",
                f"- Expectancy: **{metrics['expectancy']}**",
                f"- Recovery Factor: **{metrics['recovery_factor']}**",
                f"- Sharpe Ratio: **{metrics['sharpe_ratio']}**",
                "",
            ]
        )
    return "\n".join(summary)


def update_certification_progress() -> Dict[str, Any]:
    snapshot = build_certification_snapshot()
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    FRAMEWORK_MD.write_text(build_framework_markdown(), encoding="utf-8")
    STATUS_MD.write_text(build_status_markdown(snapshot), encoding="utf-8")
    return snapshot


def evaluate_target(required_trades: int) -> Dict[str, Any]:
    snapshot = build_certification_snapshot()
    for level in snapshot["levels"]:
        if int(level["required_trades"]) == int(required_trades):
            return level
    return {
        "name": f"{required_trades} Trade Certification",
        "required_trades": required_trades,
        "progress_trades": 0,
        "progress_pct": 0.0,
        "completed": False,
        "metrics": _metrics([]),
    }
