"""Apply configured session, regime, loss, and execution-grade trade guards."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from core.settings import KILL_SWITCH_GRACE_ENABLED, KILL_SWITCH_MIN_TRADES_BEFORE_BLOCK
except Exception:  # pragma: no cover
    # Fallback defaults if import fails (should not happen in normal operation)
    pass

# ============================================================================
# READ ALL VALUES FROM CORE.SETTINGS (Single Source of Truth)
# ============================================================================
# [FER3ON-2026-08-31] All kill-switch configuration is now centralized in
# core/settings.py. This module reads those values directly and applies only
# the decision logic, not configuration.

try:
    from core import settings as _settings

    # Master enforcement toggle
    KILL_SWITCH_ENABLED: bool = _settings.KILL_SWITCH_ENABLED

    # Session-level blocks
    SESSION_BLOCK_ENABLED: bool = _settings.KILL_SWITCH_SESSION_BLOCK_ENABLED
    BLOCKED_SESSIONS_BY_STRATEGY: Dict[str, set] = _settings.KILL_SWITCH_BLOCKED_SESSIONS

    # Regime-level blocks
    REGIME_BLOCK_ENABLED: bool = _settings.KILL_SWITCH_REGIME_BLOCK_ENABLED
    BLOCKED_REGIMES_BY_STRATEGY: Dict[str, set] = _settings.KILL_SWITCH_BLOCKED_REGIMES

    # Daily and weekly loss limits
    DAILY_LOSS_LIMIT_BY_STRATEGY: Dict[str, float] = _settings.KILL_SWITCH_DAILY_LOSS_LIMITS
    WEEKLY_LOSS_LIMIT_BY_STRATEGY: Dict[str, float] = _settings.KILL_SWITCH_WEEKLY_LOSS_LIMITS

    # Resume and grace period settings
    RESUME_AFTER_WINS: int = _settings.KILL_SWITCH_RESUME_AFTER_WINS
    MIN_TRADES_FOR_DAILY_BLOCK: int = _settings.KILL_SWITCH_MIN_TRADES_FOR_DAILY_BLOCK
    MIN_TRADES_FOR_WEEKLY_BLOCK: int = _settings.KILL_SWITCH_MIN_TRADES_FOR_WEEKLY_BLOCK
    KILL_SWITCH_GRACE_ENABLED: bool = _settings.KILL_SWITCH_GRACE_ENABLED

    # Execution grade requirements
    STRICT_EXEC_GRADE_STRATEGIES: set = _settings.KILL_SWITCH_STRICT_EXEC_GRADE_STRATEGIES
    ALLOWED_EXEC_GRADES: set = _settings.KILL_SWITCH_ALLOWED_EXEC_GRADES

except Exception:  # pragma: no cover
    # Fallback if settings import fails
    KILL_SWITCH_ENABLED: bool = False
    SESSION_BLOCK_ENABLED: bool = False
    BLOCKED_SESSIONS_BY_STRATEGY: Dict[str, set] = {
        "SMC": {"ASIA", "NEWYORK"},
        "DAILY": set(),
    }
    BLOCKED_REGIMES_BY_STRATEGY: Dict[str, set] = {
        "SMC": {"RANGING"},
        "DAILY": set(),
    }
    REGIME_BLOCK_ENABLED: bool = True
    DAILY_LOSS_LIMIT_BY_STRATEGY: Dict[str, float] = {
        "SMC": 50.0,
        "DAILY": 80.0,
    }
    WEEKLY_LOSS_LIMIT_BY_STRATEGY: Dict[str, float] = {
        "SMC": 120.0,
        "DAILY": 200.0,
    }
    RESUME_AFTER_WINS: int = 2
    MIN_TRADES_FOR_DAILY_BLOCK: int = 3
    MIN_TRADES_FOR_WEEKLY_BLOCK: int = 5
    KILL_SWITCH_GRACE_ENABLED: bool = True
    STRICT_EXEC_GRADE_STRATEGIES: set = {"SMC"}
    ALLOWED_EXEC_GRADES: set = {"A", "A+", "ELITE"}

TRADES_CSV_PATH = "data/history/trades.csv"
KILL_STATE_PATH = "data/analytics/kill_switch_state.json"


# ============================================================================
# قراءة الحالة من الملف
# ============================================================================

def _current_account_id() -> str:
    """يعيد رقم الحساب الحالي كـstring أو "" لو غير متاح."""
    try:
        from core.account_scope import get_cached_account_id

        return str(get_cached_account_id() or "")
    except Exception:
        return ""


def _read_recent_trades(hours: int = 168) -> list[dict]:
    """قراءة صفقات آخر N ساعات من trades.csv، مفلترة على البيلد والحساب الحاليين.

    [FER3ON-FIX-2026-08-31] قبل الإصلاح: صفقات من حساب قديم كانت ما زالت
    تُحسب في الـweekly_pnl/ daily_pnl للحساب الجديد لأن الفلترة الزمنية/الـ
    build-only كانت لا تكفي عندما يتغير الحساب نفسه دون تغيير build_id.
    بعد الإصلاح: نستبعد أي صف له account_id ومختلف عن الحساب الحالي، مع
    الاحتفاظ بالتوافق للخلف لصفوف فراغ account_id (غير المعرّفة) ما لم تنشأ
    ضمن build/تاريخ غير الحالي.
    """
    path = Path(TRADES_CSV_PATH)
    if not path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    trades: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = datetime.fromisoformat(row.get("date", "").replace("Z", "+00:00"))
                    if d >= cutoff:
                        trades.append(row)
                except (ValueError, TypeError):
                    continue
    except OSError:
        return []
    try:
        from core.build_scope import filter_current_build_rows

        trades = filter_current_build_rows(trades, date_field="date")
    except Exception:
        # لو الاستيراد فشل لأي سبب، نرجع لسلوك ما قبل الإصلاح بدل ما نكسر
        # الـkill-switch بالكامل — فشل الفلترة أهون من فشل الحماية.
        pass

    current_account = _current_account_id()
    if current_account:
        filtered_by_account: list[dict] = []
        for row in trades:
            account_id = str(row.get("account_id", "") or "").strip()
            if not account_id:
                # للصفوف القديمة/غير المعرّفة حسابها، نحتفظ بها فقط لو كانت
                # بالفعل ضمن build الحالي/وقت الحالي بعد الفلترة أعلاه.
                filtered_by_account.append(row)
            elif account_id == current_account:
                filtered_by_account.append(row)
        trades = filtered_by_account
    return trades


def _sum_pnl(trades: list[dict], strategy: str) -> float:
    total = 0.0
    for t in trades:
        if str(t.get("strategy", "")).upper() != strategy.upper():
            continue
        if str(t.get("result", "")).upper() not in {"WIN", "LOSS"}:
            continue
        try:
            total += float(t.get("profit", 0) or 0)
        except (ValueError, TypeError):
            continue
    return total


def _consecutive_wins(trades: list[dict], strategy: str) -> int:
    filtered = [
        t for t in trades
        if str(t.get("strategy", "")).upper() == strategy.upper()
        and str(t.get("result", "")).upper() in {"WIN", "LOSS"}
    ]
    filtered.sort(key=lambda r: r.get("date", ""), reverse=True)
    wins = 0
    for t in filtered:
        if str(t.get("result", "")).upper() == "WIN":
            wins += 1
        else:
            break
    return wins


def _strategy_trade_count(trades: list[dict], strategy: str) -> int:
    count = 0
    for t in trades:
        if str(t.get("strategy", "")).upper() != strategy.upper():
            continue
        if str(t.get("result", "")).upper() not in {"WIN", "LOSS"}:
            continue
        count += 1
    return count


# ============================================================================
# البوابة الرئيسية — تُستدعى قبل فتح كل صفقة
# ============================================================================

def should_block_trade(
    *,
    strategy: str,
    session: Optional[str] = None,
    market_regime: Optional[str] = None,
    exec_grade: Optional[str] = None,
    size_mode: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    يعيد (block, reason).
    block=True يعني ارفض فتح الصفقة، والسبب يُسجّل ويُعرض للمستخدم.
    """
    if not KILL_SWITCH_ENABLED:
        return False, "KILL_SWITCH_DISABLED"

    strat = str(strategy or "").upper()
    sess = str(session or "").upper()
    regime = str(market_regime or "").upper()
    grade = str(exec_grade or "").upper()

    # 1) جلسات ممنوعة (معطّل مؤقتًا — انظر SESSION_BLOCK_ENABLED فوق)
    if SESSION_BLOCK_ENABLED and sess and sess in BLOCKED_SESSIONS_BY_STRATEGY.get(strat, set()):
        return True, f"KILL_SWITCH_SESSION_{strat}_{sess}"

    # 2) أنظمة سوق ممنوعة
    if REGIME_BLOCK_ENABLED and regime and regime in BLOCKED_REGIMES_BY_STRATEGY.get(strat, set()):
        return True, f"KILL_SWITCH_REGIME_{strat}_{regime}"

    # 3) exec_grade مشدد للاستراتيجيات الخاسرة
    if (
        strat in STRICT_EXEC_GRADE_STRATEGIES
        and str(size_mode or "").upper() != "MICRO"
        and grade
        and grade not in ALLOWED_EXEC_GRADES
    ):
        # [FER3ON-FIX-2026-08-31] نفس grace period للحساب الجديد: لا نطبق
        # حظر exec_grade قبل وجود بيانات كافية على الحساب الفعلي.
        weekly = _read_recent_trades(hours=168)
        if _strategy_trade_count(weekly, strat) >= MIN_TRADES_FOR_WEEKLY_BLOCK and _sum_pnl(weekly, strat) < 0:
            return True, f"KILL_SWITCH_EXEC_GRADE_{strat}_{grade}_below_A"

    # 4) حد الخسارة اليومية: use broker-confirmed PnL, not delayed CSV rows.
    try:
        from core.daily_loss_guard import get_daily_loss_status
        daily_status = get_daily_loss_status(symbol=_settings.SYMBOL)
    except Exception as exc:
        return True, f"KILL_SWITCH_DAILY_PNL_UNAVAILABLE_{type(exc).__name__}"
    daily_loss = float(daily_status["daily_loss"])
    daily_limit = float(_settings.MAX_DAILY_LOSS_USD)
    if daily_loss >= daily_limit:
        return True, (
            f"KILL_SWITCH_DAILY_LOSS_{strat}_loss={daily_loss:.2f}_"
            f"limit={daily_limit:.2f}"
        )

    # 5) حد الخسارة الأسبوعية
    weekly = _read_recent_trades(hours=168)
    weekly_pnl = _sum_pnl(weekly, strat)
    weekly_limit = WEEKLY_LOSS_LIMIT_BY_STRATEGY.get(strat, 200.0)
    weekly_trade_count = _strategy_trade_count(weekly, strat)
    if weekly_trade_count >= MIN_TRADES_FOR_WEEKLY_BLOCK and weekly_pnl <= -weekly_limit:
        wins_now = _consecutive_wins(weekly, strat)
        if wins_now < RESUME_AFTER_WINS:
            return True, (
                f"KILL_SWITCH_WEEKLY_LOSS_{strat}_pnl={weekly_pnl:.2f}_"
                f"limit=-{weekly_limit:.2f}"
            )

    return False, "OK"


# ============================================================================
# تسجيل الحالة إلى ملف (للمراقبة والداشبورد)
# ============================================================================

def snapshot_state() -> Dict[str, Any]:
    """يعيد حالة الـ kill-switch لكل استراتيجية (للاستخدام في الداشبورد)"""
    now = datetime.now(timezone.utc).isoformat()
    today = _read_recent_trades(hours=24)
    week = _read_recent_trades(hours=168)
    state: Dict[str, Any] = {
        "timestamp": now,
        # [FER3ON-FIX-2026-08-20] عشان الداشبورد ما يعرضش "ASIA/NEWYORK
        # ممنوعين" وهما فعليًا مش بيتمنعوا دلوقتي.
        "session_block_enabled": SESSION_BLOCK_ENABLED,
        "strategies": {},
    }
    for strat in ("SMC", "DAILY"):
        d_pnl = _sum_pnl(today, strat)
        w_pnl = _sum_pnl(week, strat)
        d_lim = DAILY_LOSS_LIMIT_BY_STRATEGY.get(strat, 100.0)
        w_lim = WEEKLY_LOSS_LIMIT_BY_STRATEGY.get(strat, 200.0)
        state["strategies"][strat] = {
            "daily_pnl": round(d_pnl, 2),
            "daily_limit": -d_lim,
            "daily_remaining": round(d_lim + d_pnl, 2),
            "weekly_pnl": round(w_pnl, 2),
            "weekly_limit": -w_lim,
            "weekly_remaining": round(w_lim + w_pnl, 2),
            # Empty when session blocking is disabled.
            "blocked_sessions": sorted(BLOCKED_SESSIONS_BY_STRATEGY.get(strat, set())) if SESSION_BLOCK_ENABLED else [],
            "configured_blocked_sessions": sorted(BLOCKED_SESSIONS_BY_STRATEGY.get(strat, set())),
            "blocked_regimes": sorted(BLOCKED_REGIMES_BY_STRATEGY.get(strat, set())),
            "consecutive_wins": _consecutive_wins(today, strat),
        }
    try:
        os.makedirs(os.path.dirname(KILL_STATE_PATH), exist_ok=True)
        with open(KILL_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
    return state


if __name__ == "__main__":
    st = snapshot_state()
    print(json.dumps(st, indent=2, ensure_ascii=False))
