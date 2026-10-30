# =============================================================================
# FER3ON — PHASE 3 | INSTITUTIONAL DASHBOARD (Shadow Analytics)
# =============================================================================
# 5 تبويبات مؤسسية جديدة — قراءة فقط، لا تأثير على runtime.
#
# 1) Portfolio Analytics       — تحليل المحفظة الكاملة
# 2) Risk Analytics            — تحليل المخاطر المؤسسي
# 3) Strategy DNA Dashboard    — أداء وترتيب الاستراتيجيات
# 4) Session Intelligence      — أفضل الجلسات وتوقيت الدخول
# 5) Regime Intelligence       — أداء النظام في كل regime
# 6) Phase 3 Shadow Status     — حالة المكوّنات الجديدة
# =============================================================================

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    PHASE3_ANALYTICS_DIR,
    PHASE3_ENABLED,
    FINAL_BRAIN_ENABLED,
    PORTFOLIO_BRAIN_ENABLED,
    GOLD_CONTEXT_ENABLED,
    ML_SAFETY_ENABLED,
    STRATEGY_DNA_ENABLED,
    SYSTEM_HEALTH_ENABLED,
)

_DASHBOARD_FILE = os.path.join(PHASE3_ANALYTICS_DIR, "institutional_dashboard.json")


# =============================================================================
# DATA COLLECTORS
# =============================================================================

def _collect_portfolio_analytics() -> Dict[str, Any]:
    """تبويب 1: Portfolio Analytics."""
    data: Dict[str, Any] = {
        "tab": "PORTFOLIO_ANALYTICS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from core.portfolio_risk_authority import _state
        open_trades = list(getattr(_state, 'open_trades', []) or [])
        daily_pnl = getattr(_state, 'daily_pnl', 0.0)
        daily_loss = getattr(_state, 'daily_loss_amount', 0.0)
        emergency = getattr(_state, 'emergency_stop', False)

        # توزيع الاستراتيجيات
        strategy_dist: Dict[str, int] = {}
        total_exposure = 0.0
        for t in open_trades:
            s = t.get('strategy', 'UNKNOWN')
            strategy_dist[s] = strategy_dist.get(s, 0) + 1
            total_exposure += float(t.get('risk_percent', 0.75) or 0.75)

        data.update({
            "open_trades_count": len(open_trades),
            "strategy_distribution": strategy_dist,
            "total_exposure_pct": round(total_exposure, 3),
            "daily_pnl": round(daily_pnl, 4),
            "daily_loss_amount": round(daily_loss, 4),
            "emergency_stop": emergency,
            "portfolio_utilization": f"{min(100, len(open_trades) * 25):.0f}%",
        })

    except Exception as e:
        data["error"] = str(e)

    # Portfolio Brain last output
    try:
        from core.phase3.portfolio_brain import get_portfolio_brain_status
        data["portfolio_brain"] = get_portfolio_brain_status()
    except Exception:
        pass

    return data


def _collect_risk_analytics() -> Dict[str, Any]:
    """تبويب 2: Risk Analytics."""
    data: Dict[str, Any] = {
        "tab": "RISK_ANALYTICS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from core.risk_manager import get_loss_limits_status
        limits = get_loss_limits_status()
        data["loss_limits"] = limits
    except Exception as e:
        data["loss_limits_error"] = str(e)

    try:
        from core.settings import (
            MAX_RISK_PER_DAY_PERCENT,
            RISK_PER_TRADE_PERCENT,
            MAX_LOT,
            MAX_OPEN_TRADES,
            HARD_RISK_MAX_PER_TRADE,
        )
        data["risk_config"] = {
            "max_daily_risk_pct": MAX_RISK_PER_DAY_PERCENT,
            "risk_per_trade_pct": RISK_PER_TRADE_PERCENT,
            "max_lot": MAX_LOT,
            "max_open_trades": MAX_OPEN_TRADES,
            "hard_risk_max_per_trade": HARD_RISK_MAX_PER_TRADE,
        }
    except Exception:
        pass

    try:
        from core.phase3.ml_safety_framework import get_ml_safety_status
        data["ml_safety"] = get_ml_safety_status()
    except Exception:
        pass

    return data


def _collect_strategy_dna_dashboard() -> Dict[str, Any]:
    """تبويب 3: Strategy DNA Dashboard."""
    data: Dict[str, Any] = {
        "tab": "STRATEGY_DNA",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from core.phase3.strategy_dna import get_strategy_rankings, get_strategy_dna_status
        data["rankings"] = get_strategy_rankings()
        data["status"] = get_strategy_dna_status()
    except Exception as e:
        data["error"] = str(e)

    # بيانات إضافية من brain/trade_dna
    try:
        from brain.trade_dna import rank_strategies
        data["brain_rankings"] = rank_strategies()
    except Exception:
        pass

    return data


def _collect_session_intelligence() -> Dict[str, Any]:
    """تبويب 4: Session Intelligence Dashboard."""
    data: Dict[str, Any] = {
        "tab": "SESSION_INTELLIGENCE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from analytics.session_edge_analysis import analyze_session_edge
        data["session_edge"] = analyze_session_edge()
    except Exception:
        pass

    try:
        from core.phase3.adaptive_shadow_calibration import get_adaptive_shadow_status
        status = get_adaptive_shadow_status()
        data["adaptive_shadow"] = status

        # تحميل التوصيات الموجودة إذا وُجدت
        suggestions_file = status.get("suggestions_file", "")
        if suggestions_file and os.path.exists(suggestions_file):
            try:
                with open(suggestions_file, "r", encoding="utf-8") as f:
                    data["adaptive_suggestions"] = json.load(f)
            except Exception:
                pass
    except Exception:
        pass

    return data


def _collect_regime_intelligence() -> Dict[str, Any]:
    """تبويب 5: Regime Intelligence Dashboard."""
    data: Dict[str, Any] = {
        "tab": "REGIME_INTELLIGENCE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from analytics.regime_edge_analysis import analyze_regime_edge
        data["regime_edge"] = analyze_regime_edge()
    except Exception:
        pass

    try:
        from core.phase3.gold_context_layer import get_gold_context_status
        data["gold_context_config"] = get_gold_context_status()
    except Exception:
        pass

    return data


def _collect_phase3_shadow_status() -> Dict[str, Any]:
    """تبويب 6: Phase 3 Shadow Status."""
    data: Dict[str, Any] = {
        "tab": "PHASE3_SHADOW_STATUS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase3_enabled": PHASE3_ENABLED,
        "mode": "SHADOW",
        "live_authority": False,
    }

    try:
        from core.phase3.phase3_orchestrator import get_phase3_status
        data["components"] = get_phase3_status().get("components", {})
    except Exception as e:
        data["components_error"] = str(e)

    try:
        from core.phase3.final_brain import get_readiness_report
        report = get_readiness_report()
        data["final_brain_readiness"] = report

        # تقدير الوقت المتبقي
        cycles_done = report.get("requirements", {}).get("shadow_cycles_done", 0)
        cycles_req = report.get("requirements", {}).get("shadow_cycles_required", 200)
        remaining = max(0, cycles_req - cycles_done)
        data["estimated_cycles_remaining"] = remaining
        data["readiness_pct"] = report.get("readiness_score", 0.0)
    except Exception:
        pass

    try:
        from core.phase3.system_health_layer import get_system_health_summary
        data["system_health"] = get_system_health_summary()
    except Exception:
        pass

    return data


# =============================================================================
# PUBLIC API
# =============================================================================

def generate_institutional_dashboard() -> Dict[str, Any]:
    """
    يُنشئ لوحة القيادة المؤسسية الكاملة.
    قراءة فقط — لا تأثير على runtime.
    """
    dashboard = {
        "version": "phase3.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW",
        "tabs": {},
    }

    tab_collectors = {
        "portfolio_analytics":  _collect_portfolio_analytics,
        "risk_analytics":       _collect_risk_analytics,
        "strategy_dna":         _collect_strategy_dna_dashboard,
        "session_intelligence": _collect_session_intelligence,
        "regime_intelligence":  _collect_regime_intelligence,
        "phase3_status":        _collect_phase3_shadow_status,
    }

    for tab_name, collector in tab_collectors.items():
        try:
            dashboard["tabs"][tab_name] = collector()
        except Exception as e:
            dashboard["tabs"][tab_name] = {"error": str(e)}

    # حفظ اللوحة
    try:
        os.makedirs(PHASE3_ANALYTICS_DIR, exist_ok=True)
        with open(_DASHBOARD_FILE, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[DASHBOARD] Save error: {e}")

    print(
        f"[INSTITUTIONAL DASHBOARD] Generated | "
        f"Tabs={len(dashboard['tabs'])} | "
        f"Mode=SHADOW"
    )

    return dashboard


def print_dashboard_summary(dashboard: Optional[Dict[str, Any]] = None) -> None:
    """يطبع ملخصاً سريعاً للوحة القيادة."""
    if dashboard is None:
        dashboard = generate_institutional_dashboard()

    print("\n" + "=" * 65)
    print("  FER3ON — PHASE 3 INSTITUTIONAL DASHBOARD (SHADOW MODE)")
    print("=" * 65)

    # Portfolio
    pt = dashboard.get("tabs", {}).get("portfolio_analytics", {})
    print(f"\n📊 PORTFOLIO")
    print(f"   Open Trades: {pt.get('open_trades_count', 0)}")
    print(f"   Exposure: {pt.get('total_exposure_pct', 0):.2f}%")
    print(f"   Daily PnL: {pt.get('daily_pnl', 0):+.4f}")
    dist = pt.get("strategy_distribution", {})
    if dist:
        print(f"   Strategy Distribution: {dist}")

    # Phase 3 Status
    p3 = dashboard.get("tabs", {}).get("phase3_status", {})
    print(f"\n🏛 PHASE 3 SHADOW STATUS")
    print(f"   Readiness: {p3.get('readiness_pct', 0):.1f}%")
    print(f"   Cycles Remaining: {p3.get('estimated_cycles_remaining', '?')}")
    health = p3.get("system_health", {})
    print(f"   System Health: {health.get('overall_score', 0):.1f} ({health.get('overall_status', 'UNKNOWN')})")

    # Strategy DNA
    dna = dashboard.get("tabs", {}).get("strategy_dna", {})
    rankings = dna.get("rankings", [])
    if rankings:
        print(f"\n🧬 STRATEGY DNA RANKINGS")
        for r in rankings[:5]:
            print(
                f"   #{r.get('suggested_rank', '?')} {r.get('strategy', '?')} | "
                f"WR={r.get('win_rate', 0):.1%} | "
                f"DNA={r.get('dna_score', 0):.1f} | "
                f"{r.get('health', 'UNKNOWN')}"
            )

    # Final Brain
    fb = p3.get("final_brain_readiness", {})
    if fb:
        req = fb.get("requirements", {})
        print(f"\n🧠 FINAL BRAIN")
        print(f"   Shadow Cycles: {req.get('shadow_cycles_done', 0)} / {req.get('shadow_cycles_required', 200)}")
        print(f"   Accuracy: {fb.get('approval_accuracy', 0):.2%}")
        print(f"   False Reject Rate: {fb.get('false_rejection_rate', 0):.2%}")
        print(f"   Live Ready: {'✅' if fb.get('live_ready') else '❌'}")

    print("\n" + "=" * 65)
    print("  All Phase 3 components running in SHADOW MODE")
    print("  No live authority — Advisory & Logging only")
    print("=" * 65 + "\n")
