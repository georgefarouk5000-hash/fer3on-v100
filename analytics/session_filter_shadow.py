# =============================================================================
# FER3ON — Session-Aware Hard Filtering: OFFLINE historical replay
# =============================================================================
# السياق: التقرير يقترح: "لو جلسة Sydney/Tokyo تُظهر PF < 1.0 آخر 3 أشهر، لا
# تدخل فيها" كـ hard filter داخل main.py. لكن analytics/session_edge_analysis.py
# هو أيضًا موديول Phase 2 (رأس الملف: "FER3ON V3+++ — PHASE 2 | SESSION EDGE
# ANALYSIS") بنفس عقد PHASE_2_SAFETY_BOUNDARY.md تمامًا مثل regime_edge_analysis
# (انظر analytics/regime_sizing_shadow.py للتفاصيل الكاملة لنفس الحجة):
#   - "Output is advisory_only — never fed back to runtime decisions"
#   - main.py مُدرَج صراحة تحت "Files NEVER to touch in Phase 2"
#
# نفس القرار: لا نضيف hard filter حي في main.py. بدلًا من ذلك، هذا الموديول
# يُعيد تشغيل التاريخ الفعلي: "لو مُنعت الصفقات في أي جلسة أظهرت PF<1.0 على
# آخر عيّنة كافية، كم صفقة كانت ستُمنع، وما صافي ربح/خسارة تلك الصفقات
# تحديدًا؟" — هذا يُعطي رقمًا حقيقيًا لرأس المال المحفوظ (أو المفقود، لو
# تبيّن أن الفلتر كان سيمنع صفقات رابحة رغم PF التاريخي الضعيف) بدل تفعيل
# فلتر حي على افتراض غير مُختبَر.
# =============================================================================

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from analytics.performance_repository import get_all_trades
from analytics.truth_layer import TradeRecord
from core.settings import PHASE2_RANKINGS_DIR

_RANKING_PATH = os.path.join(PHASE2_RANKINGS_DIR, "session_edge_ranking.json")

PF_BLOCK_THRESHOLD = 1.0  # matches the report's own suggested threshold


def _load_ranking() -> Optional[Dict[str, Any]]:
    if not os.path.exists(_RANKING_PATH):
        return None
    try:
        with open(_RANKING_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _sessions_that_would_be_blocked(ranking: Dict[str, Any], pf_threshold: float = PF_BLOCK_THRESHOLD) -> List[str]:
    blocked = []
    for edge in ranking.get("sessions", []):
        if edge.get("sample_label") not in ("EDGE_CONFIRMED", "WEAK_EDGE"):
            continue  # never block off an insufficient/no-trade sample
        pf = edge.get("profit_factor")
        if pf is not None and pf < pf_threshold:
            blocked.append(str(edge.get("session", "")).upper())
    return blocked


def replay_session_hard_filter(
    trades: Optional[List[TradeRecord]] = None,
    ranking: Optional[Dict[str, Any]] = None,
    pf_threshold: float = PF_BLOCK_THRESHOLD,
) -> Dict[str, Any]:
    """What would have happened, historically, had every session with a
    confirmed profit_factor below pf_threshold been hard-blocked?
    """
    if trades is None:
        trades = get_all_trades()
    if ranking is None:
        ranking = _load_ranking()

    if not ranking:
        return {
            "status": "NO_RANKING_FILE",
            "message": (
                "No session_edge_ranking.json found under "
                f"{PHASE2_RANKINGS_DIR}. Run "
                "tools/generate_performance_intelligence_reports.py first."
            ),
        }
    if not trades:
        return {"status": "NO_TRADES", "message": "No closed trades in Truth Layer yet."}

    blocked_sessions = _sessions_that_would_be_blocked(ranking, pf_threshold)

    blocked_trades = [t for t in trades if (t.session or "UNKNOWN").upper() in blocked_sessions]
    kept_trades = [t for t in trades if (t.session or "UNKNOWN").upper() not in blocked_sessions]

    blocked_pnl = round(sum(float(t.profit or 0) for t in blocked_trades), 2)
    kept_pnl = round(sum(float(t.profit or 0) for t in kept_trades), 2)

    return {
        "status": "OK",
        "pf_threshold": pf_threshold,
        "blocked_sessions": blocked_sessions,
        "total_trades": len(trades),
        "trades_that_would_be_blocked": len(blocked_trades),
        "pnl_of_blocked_trades": blocked_pnl,
        "pnl_of_kept_trades": kept_pnl,
        "capital_effect_of_filter": (
            "would have avoided a net loss" if blocked_pnl < 0 else
            "would ALSO have blocked net-positive trades" if blocked_pnl > 0 else
            "no effect (breakeven)"
        ),
    }


def print_replay_report(trades: Optional[List[TradeRecord]] = None, pf_threshold: float = PF_BLOCK_THRESHOLD) -> None:
    report = replay_session_hard_filter(trades, pf_threshold=pf_threshold)
    print("=" * 70)
    print("SESSION-AWARE HARD FILTER — OFFLINE REPLAY (not live)")
    print("=" * 70)
    if report["status"] != "OK":
        print(report["message"])
        print("=" * 70)
        return
    print(f"PF block threshold          : {report['pf_threshold']}")
    print(f"Sessions that would block   : {report['blocked_sessions'] or '(none met the threshold)'}")
    print(f"Trades that would be blocked: {report['trades_that_would_be_blocked']} / {report['total_trades']}")
    print(f"P&L of those blocked trades : {report['pnl_of_blocked_trades']}")
    print(f"P&L of the kept trades      : {report['pnl_of_kept_trades']}")
    print(f"Verdict                     : {report['capital_effect_of_filter']}")
    print("=" * 70)


if __name__ == "__main__":
    print_replay_report()
