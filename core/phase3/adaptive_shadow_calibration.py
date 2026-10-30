# =============================================================================
# FER3ON — PHASE 3 | ADAPTIVE_SHADOW_CALIBRATION
# =============================================================================
# الدور: نسخة shadow آمنة من Adaptive Learning.
# الوضع الحالي: SHADOW ONLY — يوصي ولا يُفعّل.
#
# الفرق عن adaptive_learning.py الأصلي:
#   - الأصلي يُعدّل thresholds مباشرة (core system)
#   - هذا الملف يُنتج توصيات فقط في data/analytics/phase3/
#   - لا يستدعي tune_thresholds()
#   - لا يُعدّل adaptive_state.json
#   - لا يُغيّر أي قيمة runtime
#
# المخرجات (توصيات فقط):
#   - confidence_threshold_suggestions
#   - session_preferences
#   - strategy_ranking_changes
# =============================================================================

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    ADAPTIVE_SHADOW_CANNOT_CHANGE,
    ADAPTIVE_SHADOW_CONFIDENCE_SUGGESTIONS,
    ADAPTIVE_SHADOW_LOG,
    ADAPTIVE_SHADOW_ONLY,
    ADAPTIVE_SHADOW_SESSION_PREF,
    ADAPTIVE_SHADOW_STRATEGY_RANKING,
    PHASE3_ANALYTICS_DIR,
)

assert ADAPTIVE_SHADOW_ONLY, (
    "ADAPTIVE_SHADOW_CALIBRATION: Must run in shadow-only mode. "
    "ADAPTIVE_SHADOW_ONLY must be True. This component never modifies live thresholds."
)

_SHADOW_DIR = os.path.join(PHASE3_ANALYTICS_DIR, "adaptive_shadow")
_SUGGESTIONS_FILE = os.path.join(_SHADOW_DIR, "adaptive_suggestions.json")
_LOG_FILE = os.path.join(_SHADOW_DIR, "adaptive_shadow.jsonl")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AdaptiveSuggestion:
    """توصية adaptive — لا تُطبَّق تلقائياً أبداً."""
    suggestion_type: str = "UNKNOWN"   # confidence / session / strategy_rank
    current_value: Any = None
    suggested_value: Any = None
    reason: str = ""
    confidence: float = 0.0           # مدى الثقة في التوصية
    data_sample_size: int = 0
    approved_for_live: bool = False    # يبقى False في Phase 3
    timestamp: float = field(default_factory=time.time)


@dataclass
class AdaptiveShadowReport:
    """تقرير الـ shadow calibration الكامل."""
    confidence_suggestions: List[AdaptiveSuggestion] = field(default_factory=list)
    session_preferences: Dict[str, Any] = field(default_factory=dict)
    strategy_rankings: List[Dict[str, Any]] = field(default_factory=list)
    total_analyzed: int = 0
    mode: str = "SHADOW_ADVISORY_ONLY"
    cannot_change: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def _ensure_dirs() -> None:
    os.makedirs(_SHADOW_DIR, exist_ok=True)


def _analyze_confidence_thresholds(
    recent_trades: List[Dict[str, Any]],
) -> List[AdaptiveSuggestion]:
    """
    يحلّل أداء مستويات الثقة المختلفة ويُنتج توصيات.
    لا يُطبّق أي تغيير — توصيات فقط.
    """
    if not ADAPTIVE_SHADOW_CONFIDENCE_SUGGESTIONS or len(recent_trades) < 20:
        return []

    suggestions = []
    # تجميع الأداء حسب نطاقات الثقة
    buckets: Dict[str, Dict[str, int]] = {
        "30-40": {"wins": 0, "total": 0},
        "40-50": {"wins": 0, "total": 0},
        "50-60": {"wins": 0, "total": 0},
        "60-70": {"wins": 0, "total": 0},
        "70-80": {"wins": 0, "total": 0},
        "80+":   {"wins": 0, "total": 0},
    }

    for trade in recent_trades:
        conf = trade.get("confidence_pct")
        if not isinstance(conf, (int, float)) or not 0 < conf <= 100:
            continue
        won = trade.get("was_winner", False)
        bucket = (
            "30-40" if conf < 40 else
            "40-50" if conf < 50 else
            "50-60" if conf < 60 else
            "60-70" if conf < 70 else
            "70-80" if conf < 80 else
            "80+"
        )
        buckets[bucket]["total"] += 1
        if won:
            buckets[bucket]["wins"] += 1

    for bucket, stats in buckets.items():
        if stats["total"] < 5:
            continue
        wr = stats["wins"] / stats["total"]
        if wr < 0.35 and stats["total"] >= 10:
            suggestions.append(AdaptiveSuggestion(
                suggestion_type="confidence_floor_raise",
                current_value=bucket,
                suggested_value=f"Raise floor above {bucket.split('-')[0]}",
                reason=f"Win rate {wr:.1%} below 35% in bucket {bucket}",
                confidence=min(0.9, stats["total"] / 50.0),
                data_sample_size=stats["total"],
                approved_for_live=False,
            ))
        elif wr > 0.65 and stats["total"] >= 15:
            suggestions.append(AdaptiveSuggestion(
                suggestion_type="confidence_floor_opportunity",
                current_value=bucket,
                suggested_value=f"Strong performance in bucket {bucket}",
                reason=f"Win rate {wr:.1%} above 65% in bucket {bucket}",
                confidence=min(0.9, stats["total"] / 50.0),
                data_sample_size=stats["total"],
                approved_for_live=False,
            ))

    return suggestions


def _analyze_session_preferences(
    recent_trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    يحلّل أفضل الجلسات للتداول.
    توصية فقط — لا تُغيّر أي إعداد.
    """
    if not ADAPTIVE_SHADOW_SESSION_PREF or len(recent_trades) < 10:
        return {}

    session_perf: Dict[str, Dict[str, Any]] = {}
    for trade in recent_trades:
        session = trade.get("session", "UNKNOWN")
        won = trade.get("was_winner", False)
        profit = trade.get("profit", 0.0)

        if session not in session_perf:
            session_perf[session] = {"wins": 0, "total": 0, "profit": 0.0}
        session_perf[session]["total"] += 1
        session_perf[session]["profit"] += profit
        if won:
            session_perf[session]["wins"] += 1

    result = {}
    for session, stats in session_perf.items():
        if stats["total"] < 3:
            continue
        wr = stats["wins"] / stats["total"]
        result[session] = {
            "win_rate": round(wr, 4),
            "total_trades": stats["total"],
            "total_profit": round(stats["profit"], 4),
            "recommended": wr >= 0.55,
            "advisory_note": (
                f"Strong session ({wr:.1%} WR)" if wr >= 0.55 else
                f"Weak session ({wr:.1%} WR)"
            ),
        }

    return result


def _analyze_strategy_rankings(
    recent_trades: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    يُنتج ترتيب مقترح للاستراتيجيات.
    توصية فقط — لا يُغيّر سلوك الاستراتيجيات.
    """
    if not ADAPTIVE_SHADOW_STRATEGY_RANKING or len(recent_trades) < 10:
        return []

    strategy_perf: Dict[str, Dict[str, Any]] = {}
    for trade in recent_trades:
        strategy = trade.get("strategy", "UNKNOWN")
        won = trade.get("was_winner", False)
        profit = trade.get("profit", 0.0)

        if strategy not in strategy_perf:
            strategy_perf[strategy] = {"wins": 0, "total": 0, "profit": 0.0}
        strategy_perf[strategy]["total"] += 1
        strategy_perf[strategy]["profit"] += profit
        if won:
            strategy_perf[strategy]["wins"] += 1

    rankings = []
    for strategy, stats in strategy_perf.items():
        if stats["total"] < 3:
            continue
        wr = stats["wins"] / stats["total"]
        rankings.append({
            "strategy": strategy,
            "win_rate": round(wr, 4),
            "total_trades": stats["total"],
            "total_profit": round(stats["profit"], 4),
            "shadow_rank_score": round(wr * 100, 2),
            "advisory_note": (
                "Prioritize" if wr >= 0.60 else
                "Monitor" if wr >= 0.45 else
                "Review performance"
            ),
            "approved_for_live": False,  # يبقى False في Phase 3
        })

    rankings.sort(key=lambda x: x["shadow_rank_score"], reverse=True)
    for i, r in enumerate(rankings):
        r["suggested_rank"] = i + 1

    return rankings


# =============================================================================
# PUBLIC API
# =============================================================================

def run_adaptive_shadow_analysis(
    recent_trades: Optional[List[Dict[str, Any]]] = None,
) -> AdaptiveShadowReport:
    """
    التحليل الرئيسي للـ Adaptive Shadow Calibration.
    يُعيد توصيات فقط — لا يُطبّق أي تغيير على الـ runtime.

    CANNOT_CHANGE = {ADAPTIVE_SHADOW_CANNOT_CHANGE}
    """
    recent_trades = recent_trades or []

    confidence_suggestions = _analyze_confidence_thresholds(recent_trades)
    session_preferences = _analyze_session_preferences(recent_trades)
    strategy_rankings = _analyze_strategy_rankings(recent_trades)

    report = AdaptiveShadowReport(
        confidence_suggestions=confidence_suggestions,
        session_preferences=session_preferences,
        strategy_rankings=strategy_rankings,
        total_analyzed=len(recent_trades),
        mode="SHADOW_ADVISORY_ONLY",
        cannot_change=list(ADAPTIVE_SHADOW_CANNOT_CHANGE),
    )

    # تسجيل
    if ADAPTIVE_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_analyzed": len(recent_trades),
            "suggestions_count": len(confidence_suggestions),
            "sessions_analyzed": len(session_preferences),
            "strategies_ranked": len(strategy_rankings),
            "cannot_change": list(ADAPTIVE_SHADOW_CANNOT_CHANGE),
        }
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[ADAPTIVE_SHADOW] Log error: {e}")

    # حفظ التوصيات
    _save_suggestions(report)

    print(
        f"[ADAPTIVE_SHADOW] Analyzed={len(recent_trades)} | "
        f"Suggestions={len(confidence_suggestions)} | "
        f"Sessions={len(session_preferences)} | "
        f"Strategies={len(strategy_rankings)} | "
        f"Mode=ADVISORY_ONLY (no live changes)"
    )

    return report


def _save_suggestions(report: AdaptiveShadowReport) -> None:
    """يحفظ التوصيات في ملف قابل للمراجعة البشرية."""
    _ensure_dirs()
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_ADVISORY_ONLY",
        "important_notice": (
            "These are RECOMMENDATIONS ONLY. "
            "No changes are applied automatically. "
            "Human review and explicit approval required before any live activation."
        ),
        "cannot_change_in_phase3": list(ADAPTIVE_SHADOW_CANNOT_CHANGE),
        "confidence_suggestions": [asdict(s) for s in report.confidence_suggestions],
        "session_preferences": report.session_preferences,
        "strategy_rankings": report.strategy_rankings,
        "total_analyzed": report.total_analyzed,
    }
    try:
        with open(_SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ADAPTIVE_SHADOW] Suggestions save error: {e}")


def get_adaptive_shadow_status() -> Dict[str, Any]:
    """تقرير حالة Adaptive Shadow Calibration."""
    return {
        "component": "ADAPTIVE_SHADOW_CALIBRATION",
        "mode": "SHADOW_ADVISORY_ONLY",
        "shadow_only": ADAPTIVE_SHADOW_ONLY,
        "cannot_change": list(ADAPTIVE_SHADOW_CANNOT_CHANGE),
        "confidence_suggestions_enabled": ADAPTIVE_SHADOW_CONFIDENCE_SUGGESTIONS,
        "session_pref_enabled": ADAPTIVE_SHADOW_SESSION_PREF,
        "strategy_ranking_enabled": ADAPTIVE_SHADOW_STRATEGY_RANKING,
        "suggestions_file": _SUGGESTIONS_FILE,
        "notice": "Advisory only. No live threshold changes in Phase 3.",
    }
