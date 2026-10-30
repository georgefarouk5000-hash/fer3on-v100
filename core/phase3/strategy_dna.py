# =============================================================================
# FER3ON — PHASE 3 | STRATEGY_DNA (Shadow Mode)
# =============================================================================
# الدور: تحليل أداء الاستراتيجيات وترتيبها مؤسسياً.
# الوضع الحالي: SHADOW ONLY — يُغذّي FINAL_BRAIN بترتيب الاستراتيجيات.
#
# يبني على brain/trade_dna.py الموجود — لا يستبدله.
# يضيف بُعداً مؤسسياً: درجة DNA لكل استراتيجية بحسب السياق الحالي.
#
# المخرجات:
#   - strategy_rank: ترتيب الاستراتيجية الحالية (0-100)
#   - context_adjusted_score: الدرجة المعدّلة بحسب الجلسة والـ regime
#   - strategy_health: حالة صحة الاستراتيجية
# =============================================================================

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    PHASE3_STRATEGY_DNA_DIR,
    STRATEGY_DNA_BONUS_WR_ABOVE,
    STRATEGY_DNA_ENABLED,
    STRATEGY_DNA_LIVE_INFLUENCE,
    STRATEGY_DNA_LOOKBACK_TRADES,
    STRATEGY_DNA_PENALTY_WR_BELOW,
    STRATEGY_DNA_RANK_INTERVAL,
    STRATEGY_DNA_SHADOW_LOG,
)

_STATE_FILE = os.path.join(PHASE3_STRATEGY_DNA_DIR, "strategy_dna_state.json")
_SHADOW_LOG_FILE = os.path.join(PHASE3_STRATEGY_DNA_DIR, "strategy_dna_shadow.jsonl")

assert not STRATEGY_DNA_LIVE_INFLUENCE, (
    "STRATEGY_DNA: Live influence is disabled in Phase 3."
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class StrategyPerformance:
    """أداء استراتيجية واحدة."""
    strategy: str = "UNKNOWN"
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    recent_win_rate: float = 0.0  # آخر N صفقة
    best_session: str = "UNKNOWN"
    best_regime: str = "UNKNOWN"
    dna_score: float = 50.0


@dataclass
class StrategyDNAOutput:
    """مخرجات STRATEGY_DNA لـ FINAL_BRAIN."""
    strategy: str = "UNKNOWN"
    dna_rank_score: float = 50.0       # الدرجة الإجمالية (0-100)
    context_adjusted_score: float = 50.0  # المعدَّلة بالسياق الحالي
    strategy_health: str = "UNKNOWN"   # STRONG / STABLE / WEAK / RECOVERING
    rank_position: int = 3             # الترتيب بين الاستراتيجيات (1=الأفضل)
    penalty_applied: bool = False
    bonus_applied: bool = False
    mode: str = "SHADOW"
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

_DEFAULT_STATE: Dict[str, Any] = {
    "version": "phase3.0",
    "per_strategy": {},    # dict: strategy → StrategyPerformance fields
    "last_ranked_at": 0,
    "total_updates": 0,
    "last_updated": 0,
}


def _ensure_dirs() -> None:
    os.makedirs(PHASE3_STRATEGY_DNA_DIR, exist_ok=True)


def _load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(_STATE_FILE):
        return dict(_DEFAULT_STATE)
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULT_STATE, **data}
    except Exception:
        return dict(_DEFAULT_STATE)


def _save_state(state: Dict[str, Any]) -> None:
    state["last_updated"] = time.time()
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[STRATEGY_DNA] State save error: {e}")


# =============================================================================
# CORE LOGIC
# =============================================================================

def _compute_dna_score(perf: Dict[str, Any]) -> float:
    """يحسب DNA Score لاستراتيجية واحدة."""
    win_rate = perf.get("win_rate", 0.5)
    expectancy = perf.get("expectancy", 0.0)
    total_trades = perf.get("total_trades", 0)
    recent_wr = perf.get("recent_win_rate", win_rate)

    if total_trades < 5:
        return 50.0  # بيانات غير كافية

    # 1) Win rate (40%)
    wr_score = win_rate * 100 * 0.40

    # 2) Expectancy مُطبَّع (30%) — نفترض أن 2.0 = 100
    normalized_exp = min(1.0, max(-1.0, expectancy / 2.0))
    exp_score = (normalized_exp + 1.0) / 2.0 * 100 * 0.30

    # 3) Recent performance (20%)
    recent_score = recent_wr * 100 * 0.20

    # 4) Sample reliability (10%)
    reliability = min(1.0, total_trades / STRATEGY_DNA_LOOKBACK_TRADES)
    reliability_score = reliability * 100 * 0.10

    total = wr_score + exp_score + recent_score + reliability_score
    return round(min(100.0, max(0.0, total)), 2)


def _determine_strategy_health(dna_score: float, win_rate: float) -> str:
    if dna_score >= 70 and win_rate >= STRATEGY_DNA_BONUS_WR_ABOVE:
        return "STRONG"
    elif dna_score >= 50:
        return "STABLE"
    elif win_rate < STRATEGY_DNA_PENALTY_WR_BELOW:
        return "WEAK"
    else:
        return "RECOVERING"


def _apply_context_adjustment(
    base_score: float,
    strategy: str,
    session: str,
    regime: str,
    state: Dict[str, Any],
) -> float:
    """يُعدّل الدرجة بحسب الجلسة والـ regime الحاليين."""
    perf = state.get("per_strategy", {}).get(strategy, {})
    adjusted = base_score

    # مكافأة إذا كانت هذه الجلسة هي الأفضل للاستراتيجية
    if perf.get("best_session") == session:
        adjusted = min(100.0, adjusted + 5.0)

    # مكافأة إذا كان هذا الـ regime هو الأفضل
    if perf.get("best_regime") == regime:
        adjusted = min(100.0, adjusted + 5.0)

    return round(adjusted, 2)


# =============================================================================
# PUBLIC API
# =============================================================================

def record_strategy_trade(
    strategy: str,
    was_winner: bool,
    profit: float,
    session: str = "UNKNOWN",
    regime: str = "UNKNOWN",
) -> None:
    """
    يُسجّل نتيجة صفقة لتحديث DNA الاستراتيجية.
    يُستدعى عند إغلاق الصفقة — لا يُغيّر أي قرار runtime.

    V9 NOTE (DATA QUALITY): تم اكتشاف أن state حقيقي كان مُلوَّثًا بإدخالات
    اختبار (TEST_STRAT, WEAK_STRAT من تشغيل tests/test_phase3_shadow.py،
    الذي يكتب فعليًا على PHASE3_STRATEGY_DNA_DIR الحقيقي لعدم استخدامه
    tmp_path/monkeypatch لعزل بيئة الاختبار). تم تنظيف الملف تاريخيًا
    (إزالة المفاتيح غير الرسمية مرة واحدة، خارج هذه الدالة) بدل إضافة حارس
    صارم هنا — حارس بأسماء كان سيكسر اختبارات pytest شرعية تستخدم أسماء
    اختبار حرة بقصد (TestStrategyDNAShadow.test_record_and_evaluate_cycle
    وغيره)، وهذا أهم من حماية بيانات لم تتكرر إلا بسبب عيب عزل في الاختبار
    نفسه. الإصلاح الجذري الصحيح مستقبليًا: تعديل test_phase3_shadow.py
    لاستخدام tempfile (مستورد في رأس الملف فعليًا وغير مُستخدَم) بدل الكتابة
    على state الحقيقي — خارج نطاق هذا العمل الحالي.
    """
    if not STRATEGY_DNA_ENABLED:
        return

    state = _load_state()
    per_strategy = state.get("per_strategy", {})

    if strategy not in per_strategy:
        per_strategy[strategy] = {
            "strategy": strategy,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.5,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "recent_results": [],
            "recent_win_rate": 0.5,
            "best_session": "UNKNOWN",
            "best_regime": "UNKNOWN",
            "dna_score": 50.0,
        }

    perf = per_strategy[strategy]
    perf["total_trades"] += 1
    if was_winner:
        perf["wins"] += 1
        perf["avg_profit"] = (
            (perf.get("avg_profit", 0.0) * (perf["wins"] - 1) + profit) / perf["wins"]
        )
    else:
        perf["losses"] += 1
        avg_loss_old = perf.get("avg_loss", 0.0)
        losses = perf["losses"]
        perf["avg_loss"] = (avg_loss_old * (losses - 1) + abs(profit)) / losses

    perf["win_rate"] = perf["wins"] / max(1, perf["total_trades"])

    # تتبع الأداء الأخير
    recent = perf.get("recent_results", [])
    recent.append({"win": was_winner, "profit": profit, "session": session, "regime": regime})
    if len(recent) > STRATEGY_DNA_LOOKBACK_TRADES:
        recent = recent[-STRATEGY_DNA_LOOKBACK_TRADES:]
    perf["recent_results"] = recent
    recent_wins = sum(1 for r in recent if r.get("win"))
    perf["recent_win_rate"] = recent_wins / len(recent) if recent else 0.5

    # حساب Expectancy
    avg_win = perf.get("avg_profit", 0.0)
    avg_loss = perf.get("avg_loss", 1.0) or 1.0
    wr = perf["win_rate"]
    perf["expectancy"] = round(wr * avg_win - (1 - wr) * avg_loss, 4)

    # تحديث الجلسة والـ regime الأفضل
    session_perf = {}
    regime_perf = {}
    for r in recent:
        s = r.get("session", "UNKNOWN")
        rr = r.get("regime", "UNKNOWN")
        session_perf[s] = session_perf.get(s, {"wins": 0, "total": 0})
        regime_perf[rr] = regime_perf.get(rr, {"wins": 0, "total": 0})
        session_perf[s]["total"] += 1
        regime_perf[rr]["total"] += 1
        if r.get("win"):
            session_perf[s]["wins"] += 1
            regime_perf[rr]["wins"] += 1

    if session_perf:
        best_s = max(session_perf, key=lambda k: session_perf[k]["wins"] / max(1, session_perf[k]["total"]))
        perf["best_session"] = best_s
    if regime_perf:
        best_r = max(regime_perf, key=lambda k: regime_perf[k]["wins"] / max(1, regime_perf[k]["total"]))
        perf["best_regime"] = best_r

    # إعادة حساب DNA score
    perf["dna_score"] = _compute_dna_score(perf)

    state["per_strategy"] = per_strategy
    state["total_updates"] = state.get("total_updates", 0) + 1
    _save_state(state)


def evaluate_strategy_shadow(
    strategy: str,
    session: str = "UNKNOWN",
    regime: str = "UNKNOWN",
    candidate_id: Optional[str] = None,
) -> StrategyDNAOutput:
    """
    تقييم استراتيجية في وضع Shadow.
    يُعيد dna_rank_score لاستخدامه في FINAL_BRAIN.
    """
    if not STRATEGY_DNA_ENABLED:
        return StrategyDNAOutput(
            strategy=strategy,
            dna_rank_score=50.0,
            mode="DISABLED",
        )

    state = _load_state()
    per_strategy = state.get("per_strategy", {})
    perf = per_strategy.get(strategy, {})

    base_dna_score = perf.get("dna_score", 50.0)
    win_rate = perf.get("win_rate", 0.5)

    # عقوبة / مكافأة
    penalty_applied = False
    bonus_applied = False
    adjusted_score = base_dna_score

    if win_rate < STRATEGY_DNA_PENALTY_WR_BELOW and perf.get("total_trades", 0) >= 10:
        adjusted_score = max(0, adjusted_score - 10.0)
        penalty_applied = True

    if win_rate >= STRATEGY_DNA_BONUS_WR_ABOVE and perf.get("total_trades", 0) >= 10:
        adjusted_score = min(100.0, adjusted_score + 5.0)
        bonus_applied = True

    context_adjusted = _apply_context_adjustment(adjusted_score, strategy, session, regime, state)
    health = _determine_strategy_health(context_adjusted, win_rate)

    # ترتيب الاستراتيجية بين كل الاستراتيجيات المعروفة
    all_scores = [(s, d.get("dna_score", 50.0)) for s, d in per_strategy.items()]
    all_scores.sort(key=lambda x: x[1], reverse=True)
    rank_position = next(
        (i + 1 for i, (s, _) in enumerate(all_scores) if s == strategy), 999
    )

    output = StrategyDNAOutput(
        strategy=strategy,
        dna_rank_score=adjusted_score,
        context_adjusted_score=context_adjusted,
        strategy_health=health,
        rank_position=rank_position,
        penalty_applied=penalty_applied,
        bonus_applied=bonus_applied,
        mode="SHADOW",
    )

    if STRATEGY_DNA_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate_id,
            "strategy": strategy,
            "session": session,
            "regime": regime,
            "output": asdict(output),
            "perf_snapshot": {
                k: v for k, v in perf.items()
                if k != "recent_results"  # لا ندخل القائمة الطويلة في الـ log
            },
        }
        try:
            from core.trade_event_ledger import append_candidate_record
            append_candidate_record(_SHADOW_LOG_FILE, record)
        except Exception as e:
            print(f"[STRATEGY_DNA] Log error: {e}")

    print(
        f"[STRATEGY_DNA SHADOW] {strategy} | Score={adjusted_score:.1f} | "
        f"Health={health} | Rank=#{rank_position} | "
        f"WR={win_rate:.2%} | Session={session} | Regime={regime}"
    )

    return output


def get_strategy_rankings() -> List[Dict[str, Any]]:
    """يُعيد ترتيب كل الاستراتيجيات حسب DNA score."""
    state = _load_state()
    per_strategy = state.get("per_strategy", {})

    rankings = []
    for strategy, perf in per_strategy.items():
        rankings.append({
            "strategy": strategy,
            "dna_score": perf.get("dna_score", 50.0),
            "win_rate": perf.get("win_rate", 0.5),
            "total_trades": perf.get("total_trades", 0),
            "expectancy": perf.get("expectancy", 0.0),
            "health": _determine_strategy_health(
                perf.get("dna_score", 50.0), perf.get("win_rate", 0.5)
            ),
        })

    rankings.sort(key=lambda x: x["dna_score"], reverse=True)
    return rankings


def get_strategy_dna_status() -> Dict[str, Any]:
    """تقرير حالة STRATEGY_DNA."""
    state = _load_state()
    return {
        "component": "STRATEGY_DNA",
        "mode": "SHADOW",
        "enabled": STRATEGY_DNA_ENABLED,
        "live_influence": STRATEGY_DNA_LIVE_INFLUENCE,
        "total_updates": state.get("total_updates", 0),
        "strategies_tracked": len(state.get("per_strategy", {})),
        "rankings": get_strategy_rankings(),
    }
