# =============================================================================
# FER3ON AI V3.5 — TRUTH LAYER
# =============================================================================
# The single source of truth for performance analytics.
# Every report reads from here. No duplicate calculations across modules.
#
# Provides:
#   - Trade History           (persistent jsonl)
#   - Win Rate
#   - Profit Factor
#   - Expectancy
#   - Max Drawdown
#   - Strategy Breakdown
#   - Session Breakdown
#   - Regime Breakdown
#
# Phase-1 stabilization: the Truth Layer is the only authoritative analytics
# surface. Other dashboards (analytics/recovery_dashboard.py) are read-only
# views over Truth Layer data.
# =============================================================================

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.settings import (
    TRUTH_LAYER_DIR,
    TRUTH_LAYER_TRADE_HISTORY,
    TRUTH_LAYER_DAILY_REPORT,
    TRUTH_LAYER_STRATEGY_BREAKDOWN,
    TRUTH_LAYER_SESSION_BREAKDOWN,
    TRUTH_LAYER_REGIME_BREAKDOWN,
    BASE_ACCOUNT_BALANCE,
)


# =============================================================================
# FILE PATHS
# =============================================================================

def _ensure_dirs() -> None:
    Path(TRUTH_LAYER_DIR).mkdir(parents=True, exist_ok=True)


# =============================================================================
# TRADE RECORD
# =============================================================================

@dataclass
class TradeRecord:
    ticket: int
    strategy: str
    direction: str
    session: str
    regime: str
    regime_strength: float = 0.0
    open_time: str = ""
    close_time: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    lot: float = 0.0
    rr_achieved: float = 0.0
    profit: float = 0.0
    risk_percent: float = 0.0
    confidence: float = 0.0
    quality_score: float = 0.0
    ml_boost: float = 0.0
    composite_score: float = 0.0
    duration_sec: float = 0.0
    exit_reason: str = ""
    entry_reason: str = ""
    entry_conditions: List[str] = field(default_factory=list)
    is_win: bool = False
    build_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_jsonl(self) -> str:
        d = asdict(self)
        return json.dumps(d, ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TradeRecord":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


# =============================================================================
# PERSISTENCE
# =============================================================================

def _trade_path() -> str:
    _ensure_dirs()
    return TRUTH_LAYER_TRADE_HISTORY


def append_trade(record: TradeRecord) -> None:
    _ensure_dirs()
    path = _trade_path()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(record.to_jsonl() + "\n")


def load_all_trades() -> List[TradeRecord]:
    path = _trade_path()
    if not os.path.exists(path):
        return []
    out: List[TradeRecord] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(TradeRecord.from_dict(d))
            except Exception:
                continue
    return out


def filter_trades(
    trades: List[TradeRecord],
    *,
    strategy: Optional[str] = None,
    session: Optional[str] = None,
    regime: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    build_id: Optional[str] = None,
) -> List[TradeRecord]:
    out: List[TradeRecord] = []
    for t in trades:
        if strategy and t.strategy.upper() != strategy.upper():
            continue
        if session and t.session.upper() != session.upper():
            continue
        if regime and (t.regime or "").upper() != regime.upper():
            continue
        if since and (t.open_time or "") < since:
            continue
        if until and (t.close_time or "") > until:
            continue
        # DATA-INTEGRITY FIX: when build_id is given, only trades stamped
        # with that exact build count. Without this, any live consumer
        # calling filter_trades(strategy=...) silently blends trades from
        # retired pre-merge strategy versions in with the current build's
        # real trades — see core/settings.py BUILD_ID for the full
        # writeup. This bit callers hard: analytics/quant_engine.py's
        # evaluate_strategy_health() feeds a risk_multiplier computed from
        # this blend directly into live lot-sizing (core/trade_executor.py)
        # and entry scoring (core/unified_decision.py QUANT_HEALTH_* bonus/
        # penalty) — not just a cosmetic report like certification was.
        if build_id and (t.build_id or "") != build_id:
            continue
        out.append(t)
    return out


# =============================================================================
# CORE METRICS
# =============================================================================

@dataclass
class Metrics:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0.0
    total_profit: float = 0.0
    total_loss: float = 0.0
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    avg_duration_sec: float = 0.0
    max_drawdown: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _classify_trade(t: TradeRecord) -> str:
    if t.profit > 0:
        return "win"
    if t.profit < 0:
        return "loss"
    return "breakeven"


def compute_metrics(trades: List[TradeRecord]) -> Metrics:
    if not trades:
        return Metrics()

    m = Metrics()
    m.total_trades = len(trades)
    wins: List[float] = []
    losses: List[float] = []
    durations: List[float] = []
    rrs: List[float] = []
    seq_w, seq_l = 0, 0
    max_seq_w, max_seq_l = 0, 0
    equity = float(BASE_ACCOUNT_BALANCE)
    peak_equity = float(BASE_ACCOUNT_BALANCE)
    max_dd = 0.0

    for t in trades:
        kind = _classify_trade(t)
        if kind == "win":
            wins.append(t.profit)
            m.wins += 1
            seq_w += 1
            seq_l = 0
            max_seq_w = max(max_seq_w, seq_w)
        elif kind == "loss":
            losses.append(abs(t.profit))
            m.losses += 1
            seq_l += 1
            seq_w = 0
            max_seq_l = max(max_seq_l, seq_l)
        else:
            m.breakeven += 1
            seq_w = 0
            seq_l = 0

        m.total_profit += max(0.0, t.profit)
        m.total_loss += abs(min(0.0, t.profit))
        m.best_trade = max(m.best_trade, t.profit)
        m.worst_trade = min(m.worst_trade, t.profit)
        if t.rr_achieved:
            rrs.append(t.rr_achieved)
        if t.duration_sec:
            durations.append(t.duration_sec)

        equity += float(t.profit or 0)
        peak_equity = max(peak_equity, equity)
        dd = peak_equity - equity
        max_dd = max(max_dd, dd)

    m.net_pnl = m.total_profit - m.total_loss
    m.win_rate = (m.wins / m.total_trades) if m.total_trades else 0.0
    m.profit_factor = (
        (m.total_profit / m.total_loss) if m.total_loss > 0 else
        (float("inf") if m.total_profit > 0 else 0.0)
    )
    m.expectancy = (
        (m.total_profit - m.total_loss) / m.total_trades
        if m.total_trades else 0.0
    )
    m.avg_win = (sum(wins) / len(wins)) if wins else 0.0
    m.avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    m.avg_rr = (sum(rrs) / len(rrs)) if rrs else 0.0
    m.avg_duration_sec = (sum(durations) / len(durations)) if durations else 0.0
    m.max_drawdown = max_dd
    m.max_consecutive_wins = max_seq_w
    m.max_consecutive_losses = max_seq_l
    return m


# =============================================================================
# BREAKDOWNS
# =============================================================================

def breakdown_by_strategy(trades: List[TradeRecord]) -> Dict[str, Metrics]:
    out: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in trades:
        out[t.strategy.upper()].append(t)
    return {k: compute_metrics(v) for k, v in out.items()}


def breakdown_by_session(trades: List[TradeRecord]) -> Dict[str, Metrics]:
    out: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in trades:
        out[(t.session or "UNKNOWN").upper()].append(t)
    return {k: compute_metrics(v) for k, v in out.items()}


def breakdown_by_regime(trades: List[TradeRecord]) -> Dict[str, Metrics]:
    out: Dict[str, List[TradeRecord]] = defaultdict(list)
    for t in trades:
        out[(t.regime or "UNKNOWN").upper()].append(t)
    return {k: compute_metrics(v) for k, v in out.items()}


# =============================================================================
# REPORTS
# =============================================================================

def daily_report(date_str: Optional[str] = None) -> Dict[str, Any]:
    all_trades = load_all_trades()
    today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_trades = filter_trades(all_trades, since=today + "T00:00:00",
                                  until=today + "T23:59:59")
    overall = compute_metrics(today_trades)
    return {
        "date": today,
        "metrics": overall.to_dict(),
        "by_strategy": {k: v.to_dict() for k, v in breakdown_by_strategy(today_trades).items()},
        "by_session":  {k: v.to_dict() for k, v in breakdown_by_session(today_trades).items()},
        "by_regime":   {k: v.to_dict() for k, v in breakdown_by_regime(today_trades).items()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def overall_report() -> Dict[str, Any]:
    all_trades = load_all_trades()
    overall = compute_metrics(all_trades)
    return {
        "metrics": overall.to_dict(),
        "by_strategy": {k: v.to_dict() for k, v in breakdown_by_strategy(all_trades).items()},
        "by_session":  {k: v.to_dict() for k, v in breakdown_by_session(all_trades).items()},
        "by_regime":   {k: v.to_dict() for k, v in breakdown_by_regime(all_trades).items()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_daily_report(date_str: Optional[str] = None) -> Dict[str, Any]:
    _ensure_dirs()
    report = daily_report(date_str)
    date = report["date"]
    out_path = Path(TRUTH_LAYER_DAILY_REPORT)

    history: Dict[str, Any] = {}
    if out_path.exists():
        try:
            history = json.loads(out_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            history = {}

    history[date] = report
    out_path.write_text(json.dumps(history, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    persist_breakdowns(report)
    return report


def persist_breakdowns(report: Dict[str, Any]) -> None:
    _ensure_dirs()
    Path(TRUTH_LAYER_STRATEGY_BREAKDOWN).write_text(
        json.dumps(report["by_strategy"], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    Path(TRUTH_LAYER_SESSION_BREAKDOWN).write_text(
        json.dumps(report["by_session"], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    Path(TRUTH_LAYER_REGIME_BREAKDOWN).write_text(
        json.dumps(report["by_regime"], indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")


# =============================================================================
# PHASE-1 ACCEPTANCE CONDITION: Truth Layer Test
# =============================================================================

def acceptance_smoke_test() -> Dict[str, Any]:
    """Used by tests/test_truth_layer.py to verify Truth Layer basics."""
    __test_reset__()

    base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    trades = [
        TradeRecord(ticket=1, strategy="SMC", direction="BUY", session="LONDON",
                    regime="TRENDING", open_time=base_time.isoformat(),
                    close_time=(base_time.replace()).isoformat(), profit=12.0, risk_percent=0.5,
                    rr_achieved=2.0, duration_sec=300, is_win=True),
        TradeRecord(ticket=2, strategy="SMC", direction="SELL", session="LONDON",
                    regime="TRENDING", open_time=base_time.isoformat(),
                    close_time=base_time.isoformat(), profit=-6.0, risk_percent=0.5,
                    rr_achieved=1.0, duration_sec=300, is_win=False),
        TradeRecord(ticket=3, strategy="DAILY", direction="BUY", session="NEW_YORK",
                    regime="RANGING", open_time=base_time.isoformat(),
                    close_time=base_time.isoformat(), profit=3.0, risk_percent=0.2,
                    rr_achieved=2.5, duration_sec=120, is_win=True),
    ]
    for t in trades:
        append_trade(t)

    overall = compute_metrics(load_all_trades())
    return {
        "trade_count": overall.total_trades,
        "win_rate": overall.win_rate,
        "net_pnl": overall.net_pnl,
        "profit_factor": overall.profit_factor,
        "by_strategy_breakdown_present": bool(breakdown_by_strategy(load_all_trades())),
        "by_session_breakdown_present": bool(breakdown_by_session(load_all_trades())),
        "by_regime_breakdown_present": bool(breakdown_by_regime(load_all_trades())),
    }


def __test_reset__() -> None:
    """Clear the truth-layer files for testing isolation."""
    for p in [
        TRUTH_LAYER_TRADE_HISTORY,
        TRUTH_LAYER_DAILY_REPORT,
        TRUTH_LAYER_STRATEGY_BREAKDOWN,
        TRUTH_LAYER_SESSION_BREAKDOWN,
        TRUTH_LAYER_REGIME_BREAKDOWN,
    ]:
        if os.path.exists(p):
            os.remove(p)
