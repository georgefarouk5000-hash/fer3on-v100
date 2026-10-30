# =============================================================================
# FER3ON — Regime-Aware Position Sizing: OFFLINE historical replay
# =============================================================================
# السياق: التقرير المُرفَق يقترح ضرب اللوت في
# min(regime_edge.expectancy_multiplier, 1.5) داخل AdaptiveLotEngine
# (core/adaptive_lot_engine.py::calculate_adaptive_lot).
#
# لكن analytics/regime_edge_analysis.py هو موديول Phase 2 (رأس الملف يقول
# صراحة: "FER3ON V3+++ — PHASE 2 | REGIME EDGE ANALYSIS") ومُقيَّد بعقد
# PHASE_2_SAFETY_BOUNDARY.md:
#   - "Phase 2 is a read-only analytics sidecar... zero runtime influence."
#   - PHASE2_RUNTIME_INFLUENCE = False   # NEVER flip to True
#   - كل RegimeEdge يحمل advisory_only=True, not_applied_live=True بالتصميم.
#   - main.py (الذي يحسب اللوت الفعلي عبر
#     core/adaptive_lot_engine.py) مُدرَجان صراحة تحت
#     "Files NEVER to touch in Phase 2".
#
# القرار هنا: احترام هذا القيد الصريح المتعمد في المشروع نفسه بدل تنفيذ
# اقتراح خارجي عابر يكسره. الحل: بدل حقن معامل حي في مسار التنفيذ، هذا
# الموديول يُعيد تشغيل (replay) تاريخ الصفقات المُغلَقة الفعلي (الآن يحمل
# market_regime لكل صفقة بفضل إصلاح enrichment) ويحسب: "لو كان معامل
# regime edge مُطبَّقًا وقتها، ماذا كانت النتيجة التراكمية؟" — بيانات حقيقية
# offline بالكامل، صفر تأثير على أي قرار حي، صفر لمس لأي ملف مذكور في
# PHASE_2_SAFETY_BOUNDARY.md كـ "never touch". هذا فعليًا أقوى من "ظل حي"
# لأنه يعمل فورًا على التاريخ الموجود بدل انتظار تراكم صفقات جديدة تحت ظل.
#
# الترقية إلى تأثير حي فعلي (إن رغب المستخدم لاحقًا، بعد مراجعة هذا التقرير)
# قرار واعٍ منفصل تمامًا عن هذا التنفيذ: يتطلب تعديل PHASE_2_SAFETY_BOUNDARY.md
# نفسه ونقل الموديول لطبقة V-next بنفس نمط analytics/quant_engine.py (الذي
# يوثّق صراحة أنه -بعكس Phase 2- له تأثير حي متعمد)، ثم فقط عندها ربطه بـ
# core/adaptive_lot_engine.py.
# =============================================================================

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from analytics.performance_repository import get_all_trades
from analytics.truth_layer import TradeRecord
from core.settings import PHASE2_RANKINGS_DIR

_RANKING_PATH = os.path.join(PHASE2_RANKINGS_DIR, "regime_edge_ranking.json")

_MULTIPLIER_MIN = 0.5
_MULTIPLIER_MAX = 1.5  # same ceiling the report itself suggested
_REFERENCE_PROFIT_FACTOR = 1.5  # PF at which the shadow multiplier is neutral (1.0)


def _load_ranking() -> Optional[Dict[str, Any]]:
    """Reads the already-persisted Phase 2 ranking JSON. Does NOT call
    analyse_regimes() -- if the report hasn't been generated yet, this
    returns None and the caller degrades gracefully (report says: run
    tools/generate_performance_intelligence_reports.py first)."""
    if not os.path.exists(_RANKING_PATH):
        return None
    try:
        with open(_RANKING_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _find_regime_edge(ranking: Dict[str, Any], market_regime: str) -> Optional[Dict[str, Any]]:
    target = (market_regime or "UNKNOWN").upper()
    for edge in ranking.get("regimes", []):
        if str(edge.get("regime", "")).upper() == target:
            return edge
    return None


def multiplier_for_regime(market_regime: str, ranking: Dict[str, Any]) -> Dict[str, Any]:
    """What a regime-edge sizing multiplier would be for one regime. A
    thin/insufficient sample always yields a neutral 1.0 -- no confident
    up- or down-sizing off weak evidence, replay or otherwise.
    """
    edge = _find_regime_edge(ranking, market_regime)
    if not edge:
        return {"multiplier": 1.0, "sample_label": "REGIME_NOT_FOUND", "profit_factor": None}

    sample_label = edge.get("sample_label", "INSUFFICIENT_SAMPLE")
    if sample_label not in ("EDGE_CONFIRMED", "WEAK_EDGE"):
        return {"multiplier": 1.0, "sample_label": sample_label, "profit_factor": edge.get("profit_factor")}

    pf = edge.get("profit_factor")
    if pf is None or pf <= 0:
        multiplier = 1.0
    else:
        multiplier = max(_MULTIPLIER_MIN, min(_MULTIPLIER_MAX, pf / _REFERENCE_PROFIT_FACTOR))

    return {"multiplier": round(multiplier, 3), "sample_label": sample_label, "profit_factor": pf}


def replay_regime_aware_sizing(
    trades: Optional[List[TradeRecord]] = None,
    ranking: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Offline replay: for every closed trade with a known lot/profit/regime,
    approximate what its P&L would have been at the regime-edge-adjusted
    lot size instead of the lot actually used, then sum up actual vs.
    counterfactual. Approximation: P&L scales linearly with lot size
    (profit_shadow = profit_actual * multiplier) -- true for a fixed-R
    trade with linear position sizing, which is this project's model; it
    is an approximation, not an exact re-simulation of spread/slippage at
    a different size, and is reported as such.
    """
    if trades is None:
        trades = get_all_trades()
    if ranking is None:
        ranking = _load_ranking()

    if not ranking:
        return {
            "status": "NO_RANKING_FILE",
            "message": (
                "No regime_edge_ranking.json found under "
                f"{PHASE2_RANKINGS_DIR}. Run "
                "tools/generate_performance_intelligence_reports.py first."
            ),
        }

    if not trades:
        return {"status": "NO_TRADES", "message": "No closed trades in Truth Layer yet."}

    total_actual_pnl = 0.0
    total_shadow_pnl = 0.0
    per_regime: Dict[str, Dict[str, Any]] = {}

    for t in trades:
        regime = (t.regime or "UNKNOWN").upper()
        info = multiplier_for_regime(regime, ranking)
        multiplier = info["multiplier"]

        actual_pnl = float(t.profit or 0)
        shadow_pnl = actual_pnl * multiplier

        total_actual_pnl += actual_pnl
        total_shadow_pnl += shadow_pnl

        bucket = per_regime.setdefault(regime, {
            "trades": 0, "sample_label": info["sample_label"],
            "multiplier": multiplier, "actual_pnl": 0.0, "shadow_pnl": 0.0,
        })
        bucket["trades"] += 1
        bucket["actual_pnl"] += actual_pnl
        bucket["shadow_pnl"] += shadow_pnl

    for bucket in per_regime.values():
        bucket["actual_pnl"] = round(bucket["actual_pnl"], 2)
        bucket["shadow_pnl"] = round(bucket["shadow_pnl"], 2)
        bucket["delta"] = round(bucket["shadow_pnl"] - bucket["actual_pnl"], 2)

    return {
        "status": "OK",
        "total_trades": len(trades),
        "total_actual_pnl": round(total_actual_pnl, 2),
        "total_shadow_pnl_if_regime_aware": round(total_shadow_pnl, 2),
        "delta": round(total_shadow_pnl - total_actual_pnl, 2),
        "per_regime": per_regime,
        "note": (
            "Approximation only: assumes linear scaling of P&L with lot "
            "size at the same entry/exit; does not re-simulate spread/"
            "slippage at a different size, and multiplier applies "
            "uniformly per regime rather than trade-by-trade with real "
            "regime_strength weighting."
        ),
    }


def print_replay_report(trades: Optional[List[TradeRecord]] = None) -> None:
    report = replay_regime_aware_sizing(trades)
    print("=" * 70)
    print("REGIME-AWARE POSITION SIZING — OFFLINE REPLAY (not live)")
    print("=" * 70)
    if report["status"] != "OK":
        print(report["message"])
        print("=" * 70)
        return
    print(f"Trades replayed        : {report['total_trades']}")
    print(f"Actual total P&L       : {report['total_actual_pnl']}")
    print(f"Shadow (regime-aware)  : {report['total_shadow_pnl_if_regime_aware']}")
    print(f"Delta                  : {report['delta']:+.2f}")
    print("-" * 70)
    for regime, bucket in report["per_regime"].items():
        print(
            f"{regime:>10} | n={bucket['trades']:>4} "
            f"sample={bucket['sample_label']:<20} mult={bucket['multiplier']:.2f} "
            f"actual={bucket['actual_pnl']:>9.2f} shadow={bucket['shadow_pnl']:>9.2f} "
            f"delta={bucket['delta']:>+8.2f}"
        )
    print("-" * 70)
    print(report["note"])
    print("=" * 70)


if __name__ == "__main__":
    print_replay_report()
