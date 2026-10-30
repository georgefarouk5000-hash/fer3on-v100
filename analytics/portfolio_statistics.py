# =============================================================================
# FER3ON V3+++ — PHASE 2 | PORTFOLIO STATISTICS
# =============================================================================
# Computes portfolio-level statistics: expectancy, drawdown curve,
# profit factor, exposure diagnostics, rolling windows.
#
# SAFETY CONTRACT:
#   ✅ Read-only — Truth Layer source only
#   ✅ No calls to evaluate_risk(), record_trade_open/close()
#   ✅ No imports from portfolio_risk_authority for write operations
#   ✅ Diagnostics only — no runtime feedback
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from analytics.performance_repository import get_all_trades, get_overall_metrics, safe_metrics_dict
from analytics.truth_layer import TradeRecord, compute_metrics
from core.settings import (
    BASE_ACCOUNT_BALANCE,
    PHASE2_REPORTS_DIR,
    PHASE2_MIN_SAMPLE_PER_BUCKET,
)


# =============================================================================
# ROLLING WINDOW ANALYSIS
# =============================================================================

ROLLING_WINDOWS = [10, 20, 50]


@dataclass
class RollingWindow:
    window: int
    win_rate: float
    profit_factor: Optional[float]
    expectancy: float
    net_pnl: float
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _rolling(trades: List[TradeRecord], window: int) -> Optional[RollingWindow]:
    if len(trades) < window:
        return None
    subset = trades[-window:]
    m = compute_metrics(subset)
    pf = m.profit_factor if m.profit_factor != float("inf") else None
    return RollingWindow(
        window=window,
        win_rate=m.win_rate,
        profit_factor=pf,
        expectancy=m.expectancy,
        net_pnl=m.net_pnl,
        sample_size=len(subset),
    )


# =============================================================================
# EQUITY CURVE & DRAWDOWN
# =============================================================================

@dataclass
class EquityPoint:
    trade_index: int
    ticket: int
    profit: float
    equity: float
    drawdown_from_peak: float
    drawdown_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_equity_curve(
    trades: List[TradeRecord],
    starting_balance: float = BASE_ACCOUNT_BALANCE,
) -> Tuple[List[EquityPoint], float, float]:
    """
    Returns (curve_points, max_drawdown_abs, max_drawdown_pct).
    """
    equity = float(starting_balance)
    peak = float(starting_balance)
    max_dd = 0.0
    max_dd_pct = 0.0
    points: List[EquityPoint] = []

    for i, t in enumerate(trades):
        equity += float(t.profit or 0)
        peak = max(peak, equity)
        dd = peak - equity
        dd_pct = (dd / peak) if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        max_dd_pct = max(max_dd_pct, dd_pct)
        points.append(EquityPoint(
            trade_index=i + 1,
            ticket=t.ticket,
            profit=t.profit,
            equity=round(equity, 2),
            drawdown_from_peak=round(dd, 2),
            drawdown_pct=round(dd_pct, 4),
        ))

    return points, round(max_dd, 2), round(max_dd_pct, 4)


# =============================================================================
# EXPOSURE DIAGNOSTICS
# =============================================================================

@dataclass
class ExposureDiagnostics:
    total_trades: int
    strategy_distribution: Dict[str, int]       # count per strategy
    session_distribution: Dict[str, int]
    regime_distribution: Dict[str, int]
    direction_distribution: Dict[str, int]
    avg_lot: float
    avg_risk_percent: float
    avg_duration_hours: float
    concentration_flag: bool    # True if any single bucket > 60% of trades
    concentration_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _distribution(trades: List[TradeRecord], attr: str) -> Dict[str, int]:
    from collections import Counter
    return dict(Counter(str(getattr(t, attr, "UNKNOWN") or "UNKNOWN").upper() for t in trades))


def build_exposure_diagnostics(trades: List[TradeRecord]) -> ExposureDiagnostics:
    n = len(trades)
    if n == 0:
        return ExposureDiagnostics(
            total_trades=0,
            strategy_distribution={},
            session_distribution={},
            regime_distribution={},
            direction_distribution={},
            avg_lot=0.0,
            avg_risk_percent=0.0,
            avg_duration_hours=0.0,
            concentration_flag=False,
            concentration_notes=["No trades available."],
        )

    strategy_dist = _distribution(trades, "strategy")
    session_dist  = _distribution(trades, "session")
    regime_dist   = _distribution(trades, "regime")
    dir_dist      = _distribution(trades, "direction")

    lots = [t.lot for t in trades if t.lot]
    risks = [t.risk_percent for t in trades if t.risk_percent]
    durations_h = [t.duration_sec / 3600.0 for t in trades if t.duration_sec]

    # Concentration check: any single bucket > 60%
    notes: List[str] = []
    flag = False
    for label, dist in [
        ("Strategy", strategy_dist),
        ("Session", session_dist),
        ("Regime", regime_dist),
    ]:
        for k, v in dist.items():
            pct = v / n
            if pct > 0.60:
                flag = True
                notes.append(f"{label}={k} is {pct:.0%} of all trades — high concentration.")

    if not notes:
        notes.append("No concentration issues detected.")

    return ExposureDiagnostics(
        total_trades=n,
        strategy_distribution=strategy_dist,
        session_distribution=session_dist,
        regime_distribution=regime_dist,
        direction_distribution=dir_dist,
        avg_lot=round(sum(lots) / len(lots), 4) if lots else 0.0,
        avg_risk_percent=round(sum(risks) / len(risks), 4) if risks else 0.0,
        avg_duration_hours=round(sum(durations_h) / len(durations_h), 2) if durations_h else 0.0,
        concentration_flag=flag,
        concentration_notes=notes,
    )


# =============================================================================
# FULL PORTFOLIO REPORT
# =============================================================================

@dataclass
class PortfolioStatistics:
    generated_at: str
    total_trades: int
    starting_balance: float
    overall_metrics: Dict[str, Any]
    equity_curve_summary: Dict[str, Any]          # high-level; full curve in separate file
    rolling_windows: List[Dict[str, Any]]
    exposure_diagnostics: Dict[str, Any]
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_portfolio_statistics(
    trades=None,
    starting_balance: float = BASE_ACCOUNT_BALANCE,
) -> PortfolioStatistics:
    if trades is None:
        trades = get_all_trades()

    overall = compute_metrics(trades)
    curve, max_dd_abs, max_dd_pct = build_equity_curve(trades, starting_balance)
    exposure = build_exposure_diagnostics(trades)

    final_equity = (
        curve[-1].equity if curve else starting_balance
    )
    total_return_pct = (
        (final_equity - starting_balance) / starting_balance
        if starting_balance > 0 else 0.0
    )

    rolling: List[Dict[str, Any]] = []
    for w in ROLLING_WINDOWS:
        rw = _rolling(trades, w)
        if rw:
            rolling.append(rw.to_dict())

    pf = overall.profit_factor if overall.profit_factor != float("inf") else None

    equity_summary = {
        "starting_balance": starting_balance,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 4),
        "max_drawdown_abs": max_dd_abs,
        "max_drawdown_pct": max_dd_pct,
        "total_data_points": len(curve),
    }

    return PortfolioStatistics(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trades=len(trades),
        starting_balance=starting_balance,
        overall_metrics=safe_metrics_dict(overall),
        equity_curve_summary=equity_summary,
        rolling_windows=rolling,
        exposure_diagnostics=exposure.to_dict(),
    )


# =============================================================================
# PERSIST
# =============================================================================

def persist_portfolio_statistics(
    stats: Optional[PortfolioStatistics] = None,
    trades=None,
) -> str:
    if stats is None:
        stats = build_portfolio_statistics(trades)
    os.makedirs(PHASE2_REPORTS_DIR, exist_ok=True)
    path = os.path.join(PHASE2_REPORTS_DIR, "portfolio_statistics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    return path


# =============================================================================
# CLI
# =============================================================================

def print_portfolio_summary(stats: Optional[PortfolioStatistics] = None) -> None:
    if stats is None:
        stats = build_portfolio_statistics()
    m = stats.overall_metrics
    e = stats.equity_curve_summary
    print(f"\n{'='*60}")
    print(f"PORTFOLIO STATISTICS  [{stats.generated_at[:19]}]")
    print(f"advisory_only=True  not_applied_live=True")
    print(f"{'='*60}")
    print(f"  Trades       : {stats.total_trades}")
    print(f"  Win Rate     : {m.get('win_rate', 0):.1%}")
    pf = m.get('profit_factor')
    print(f"  Profit Factor: {pf:.2f}" if pf is not None else "  Profit Factor: ∞")
    print(f"  Expectancy   : {m.get('expectancy', 0):+.2f}")
    print(f"  Net PnL      : {m.get('net_pnl', 0):+.2f}")
    print(f"  Max Drawdown : {e.get('max_drawdown_abs', 0):.2f}  ({e.get('max_drawdown_pct', 0):.1%})")
    print(f"  Total Return : {e.get('total_return_pct', 0):.2%}")
    print()
    if stats.rolling_windows:
        print("  Rolling Windows:")
        for rw in stats.rolling_windows:
            pf2 = f"{rw['profit_factor']:.2f}" if rw['profit_factor'] is not None else "∞"
            print(
                f"    L{rw['window']:<4}: WR={rw['win_rate']:.1%}  "
                f"PF={pf2}  Exp={rw['expectancy']:+.2f}"
            )
    print()
    exp = stats.exposure_diagnostics
    if exp.get("concentration_flag"):
        print("  ⚠ CONCENTRATION WARNING:")
        for note in exp.get("concentration_notes", []):
            print(f"    {note}")
    else:
        print(f"  Exposure: No concentration issues detected.")
    print()


if __name__ == "__main__":
    s = build_portfolio_statistics()
    print_portfolio_summary(s)
    path = persist_portfolio_statistics(s)
    print(f"Saved → {path}")
