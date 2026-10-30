# =============================================================================
# FER3ON — PHASE 3 | SHADOW ORCHESTRATOR
# =============================================================================
# الدور: نقطة الدخول الموحّدة لتشغيل كل مكوّنات Phase 3 في Shadow Mode.
#
# يُستدعى من main.py بعد قرار المنظومة الحالية — لا يُغيّر القرار.
# يجمع مخرجات كل المكوّنات ويكتبها في data/analytics/phase3/
#
# تسلسل التشغيل:
#   1) PORTFOLIO_BRAIN.evaluate_portfolio_shadow()
#   2) GOLD_CONTEXT_LAYER.evaluate_gold_context()
#   3) ML_SAFETY.record_ml_prediction()
#   4) STRATEGY_DNA.evaluate_strategy_shadow()
#   5) FINAL_BRAIN.evaluate_shadow()   ← يستخدم مخرجات كل ما سبق
#   6) SYSTEM_HEALTH (دوري فقط)
#   7) ADAPTIVE_SHADOW_CALIBRATION (دوري فقط)
#
# القاعدة الذهبية:
#   إذا حدث أي خطأ في Phase 3 → لا يتأثر runtime الأصلي.
#   Phase 3 = sidecar كامل الاستقلال.
# =============================================================================

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.settings import (
    FINAL_BRAIN_ENABLED,
    GOLD_CONTEXT_ENABLED,
    ML_SAFETY_ENABLED,
    PHASE3_ENABLED,
    PORTFOLIO_BRAIN_ENABLED,
    STRATEGY_DNA_ENABLED,
    SYSTEM_HEALTH_ENABLED,
)


# =============================================================================
# ORCHESTRATOR INPUT / OUTPUT
# =============================================================================

@dataclass
class Phase3Input:
    """
    مدخلات Phase 3 Orchestrator.
    تُعبّر عن حالة النظام والقرار الفعلي.
    """
    # معلومات الصفقة / الإعداد
    strategy: str = "UNKNOWN"
    signal: str = "NONE"
    symbol: str = "XAUUSD"
    candidate_id: str = ""
    quality_score: float = 0.0
    confidence_pct: float = 0.0
    composite_score: float = 0.0

    # القرار الفعلي من المنظومة (لا نُغيّره)
    actual_decision: str = "UNKNOWN"   # FULL / REDUCED / MICRO / HARD_BLOCK / WAIT

    # حالة المحفظة
    open_trades: List[Dict[str, Any]] = field(default_factory=list)
    account_balance: float = 1000.0
    equity: float = 1000.0

    # عوامل السياق
    session: str = "UNKNOWN"
    market_regime: str = "UNKNOWN"
    ml_score: float = 50.0

    # عوامل ماكرو الذهب (اختياري)
    gold_macro_factors: Optional[Any] = None   # GoldMacroFactors إذا متاحة

    timestamp: float = field(default_factory=time.time)


@dataclass
class Phase3Output:
    """
    مخرجات Phase 3 Orchestrator.
    كلها shadow — لا تأثير على runtime.
    """
    # مخرجات المكوّنات
    portfolio_brain_score: float = 50.0
    gold_context_score: float = 50.0
    ml_health_score: float = 50.0
    strategy_dna_rank: float = 50.0

    # القرار النهائي لـ FINAL_BRAIN (shadow)
    final_brain_decision: str = "SHADOW_DISABLED"
    final_brain_score: float = 0.0
    matched_actual: bool = False

    # تحذيرات ومعلومات
    warnings: List[str] = field(default_factory=list)
    components_run: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # الوضع
    mode: str = "SHADOW"
    phase3_active: bool = True
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# ORCHESTRATOR CORE
# =============================================================================

_ADAPTIVE_ANALYSIS_INTERVAL = 50   # تشغيل adaptive shadow كل 50 دورة
_HEALTH_CHECK_CYCLE = 0            # عداد لضبط فحص الصحة
_adaptive_cycle_count = 0


def run_phase3_shadow(inp: Phase3Input) -> Phase3Output:
    """
    تشغيل كامل دورة Phase 3 Shadow.

    يُستدعى من main.py كـ sidecar بعد قرار المنظومة.
    أي خطأ في هذه الدالة لا يُوقف runtime الأصلي.
    """
    global _adaptive_cycle_count

    if not PHASE3_ENABLED:
        return Phase3Output(phase3_active=False, mode="DISABLED")

    output = Phase3Output()
    _adaptive_cycle_count += 1

    # =========================================================================
    # 1) PORTFOLIO_BRAIN
    # =========================================================================
    if PORTFOLIO_BRAIN_ENABLED:
        try:
            from core.phase3.portfolio_brain import evaluate_portfolio_shadow
            pb_out = evaluate_portfolio_shadow(
                open_trades=inp.open_trades,
                account_balance=inp.account_balance,
                equity=inp.equity,
                candidate_id=inp.candidate_id or None,
            )
            output.portfolio_brain_score = pb_out.portfolio_brain_score
            output.warnings.extend(pb_out.warnings)
            output.components_run.append("PORTFOLIO_BRAIN")
        except Exception as e:
            output.errors.append(f"PORTFOLIO_BRAIN: {e}")
            output.portfolio_brain_score = 50.0

    # =========================================================================
    # 2) GOLD_CONTEXT_LAYER
    # =========================================================================
    if GOLD_CONTEXT_ENABLED:
        try:
            from core.phase3.gold_context_layer import (
                evaluate_gold_context,
                load_gold_macro_factors,
            )
            if inp.gold_macro_factors is not None:
                factors = inp.gold_macro_factors
            else:
                factors, macro_status = load_gold_macro_factors()
                if factors is None:
                    output.warnings.append(f"GOLD_CONTEXT: {macro_status}")
            gc_out = evaluate_gold_context(
                factors=factors,
                signal=inp.signal,
                candidate_id=inp.candidate_id or None,
            )
            output.gold_context_score = gc_out.gold_context_score
            output.warnings.extend(gc_out.warnings)
            output.components_run.append("GOLD_CONTEXT_LAYER")
        except Exception as e:
            output.errors.append(f"GOLD_CONTEXT: {e}")
            output.gold_context_score = 50.0

    # =========================================================================
    # 3) ML_SAFETY (تسجيل تنبؤ)
    # =========================================================================
    if ML_SAFETY_ENABLED:
        try:
            from core.phase3.ml_safety_framework import (
                record_ml_prediction,
                run_health_check,
                should_run_health_check,
            )
            record_ml_prediction(
                prediction_score=inp.ml_score,
                strategy=inp.strategy,
                session=inp.session,
                regime=inp.market_regime,
            )
            # فحص دوري للصحة
            if should_run_health_check():
                ml_report = run_health_check()
                output.ml_health_score = ml_report.health_score
                output.warnings.extend(ml_report.warnings)
            else:
                output.ml_health_score = 70.0  # افتراضي إيجابي حتى الفحص القادم
            output.components_run.append("ML_SAFETY")
        except Exception as e:
            output.errors.append(f"ML_SAFETY: {e}")
            output.ml_health_score = 50.0

    # =========================================================================
    # 4) STRATEGY_DNA
    # =========================================================================
    if STRATEGY_DNA_ENABLED:
        try:
            from core.phase3.strategy_dna import evaluate_strategy_shadow
            dna_out = evaluate_strategy_shadow(
                strategy=inp.strategy,
                session=inp.session,
                regime=inp.market_regime,
                candidate_id=inp.candidate_id or None,
            )
            output.strategy_dna_rank = dna_out.context_adjusted_score
            output.components_run.append("STRATEGY_DNA")
        except Exception as e:
            output.errors.append(f"STRATEGY_DNA: {e}")
            output.strategy_dna_rank = 50.0

    # =========================================================================
    # 5) FINAL_BRAIN (يستخدم مخرجات كل ما سبق)
    # =========================================================================
    if FINAL_BRAIN_ENABLED:
        try:
            from core.phase3.final_brain import FinalBrainInput, evaluate_shadow
            fb_inp = FinalBrainInput(
                strategy=inp.strategy,
                signal=inp.signal,
                symbol=inp.symbol,
                quality_score=inp.quality_score,
                confidence_pct=inp.confidence_pct,
                composite_score=inp.composite_score,
                actual_decision=inp.actual_decision,
                portfolio_brain_score=output.portfolio_brain_score,
                gold_context_score=output.gold_context_score,
                ml_health_score=output.ml_health_score,
                strategy_dna_rank=output.strategy_dna_rank,
                session=inp.session,
                market_regime=inp.market_regime,
                extra={"candidate_id": inp.candidate_id},
            )
            fb_out = evaluate_shadow(fb_inp)
            output.final_brain_decision = fb_out.shadow_decision
            output.final_brain_score = fb_out.approval_score
            output.matched_actual = fb_out.matched_actual
            output.components_run.append("FINAL_BRAIN")
        except Exception as e:
            output.errors.append(f"FINAL_BRAIN: {e}")
            output.final_brain_decision = "SHADOW_ERROR"

    # =========================================================================
    # 6) SYSTEM_HEALTH (دوري)
    # =========================================================================
    if SYSTEM_HEALTH_ENABLED:
        try:
            from core.phase3.system_health_layer import should_run_health_check, run_system_health_check
            if should_run_health_check():
                health_report = run_system_health_check()
                output.warnings.extend(health_report.active_warnings)
                if health_report.active_alerts:
                    output.errors.extend([f"HEALTH_ALERT: {a}" for a in health_report.active_alerts])
                output.components_run.append("SYSTEM_HEALTH")
        except Exception as e:
            output.errors.append(f"SYSTEM_HEALTH: {e}")

    # =========================================================================
    # 7) ADAPTIVE_SHADOW_CALIBRATION (دوري — كل N دورة)
    # =========================================================================
    if _adaptive_cycle_count % _ADAPTIVE_ANALYSIS_INTERVAL == 0:
        try:
            from core.phase3.adaptive_shadow_calibration import run_adaptive_shadow_analysis
            from analytics.performance_repository import get_all_trades

            recent_trades = []
            for trade in get_all_trades():
                if not trade.close_time:
                    continue
                try:
                    confidence = float(trade.confidence)
                    profit = float(trade.profit)
                except (TypeError, ValueError):
                    confidence = 0.0
                    try:
                        profit = float(trade.profit)
                    except (TypeError, ValueError):
                        continue
                if not math.isfinite(profit):
                    continue
                sample = {
                    "was_winner": profit > 0,
                    "profit": profit,
                    "session": trade.session,
                    "strategy": trade.strategy,
                }
                if 0 < confidence <= 1:
                    sample["confidence_pct"] = confidence * 100
                elif 0 < confidence <= 100:
                    sample["confidence_pct"] = confidence
                recent_trades.append(sample)
            run_adaptive_shadow_analysis(recent_trades=recent_trades)
            output.components_run.append("ADAPTIVE_SHADOW")
        except Exception as e:
            output.errors.append(f"ADAPTIVE_SHADOW: {e}")

    # =========================================================================
    # الناتج النهائي
    # =========================================================================
    if output.errors:
        print(f"[PHASE3 SHADOW] Errors (non-critical): {' | '.join(output.errors)}")

    print(
        f"[PHASE3 SHADOW ✓] Components={len(output.components_run)} | "
        f"FinalBrain={output.final_brain_decision} ({output.final_brain_score:.1f}) | "
        f"Portfolio={output.portfolio_brain_score:.1f} | "
        f"GoldCtx={output.gold_context_score:.1f} | "
        f"StrategyDNA={output.strategy_dna_rank:.1f} | "
        f"Matched={output.matched_actual}"
    )

    return output


def notify_trade_closed(
    ticket: int,
    strategy: str,
    session: str,
    regime: str,
    was_winner: bool,
    profit: float,
    shadow_final_brain_decision: str = "UNKNOWN",
    ml_prediction_timestamp: float = 0.0,
) -> None:
    """
    يُشعر Phase 3 بإغلاق صفقة لتحديث السجلات.
    يُستدعى من main.py عند إغلاق أي صفقة.
    """
    if not PHASE3_ENABLED:
        return

    # تحديث STRATEGY_DNA
    if STRATEGY_DNA_ENABLED:
        try:
            from core.phase3.strategy_dna import record_strategy_trade
            record_strategy_trade(
                strategy=strategy,
                was_winner=was_winner,
                profit=profit,
                session=session,
                regime=regime,
            )
        except Exception as e:
            print(f"[PHASE3] STRATEGY_DNA close update error: {e}")

    # تحديث FINAL_BRAIN (false rejection tracking)
    if FINAL_BRAIN_ENABLED and shadow_final_brain_decision:
        try:
            from core.phase3.final_brain import record_trade_outcome
            record_trade_outcome(
                ticket=ticket,
                was_winner=was_winner,
                shadow_decision=shadow_final_brain_decision,
            )
        except Exception as e:
            print(f"[PHASE3] FINAL_BRAIN close update error: {e}")

    # تحديث ML_SAFETY
    if ML_SAFETY_ENABLED and ml_prediction_timestamp:
        try:
            from core.phase3.ml_safety_framework import resolve_ml_prediction
            resolve_ml_prediction(
                timestamp=ml_prediction_timestamp,
                was_winner=was_winner,
            )
        except Exception as e:
            print(f"[PHASE3] ML_SAFETY close update error: {e}")


def get_phase3_status() -> Dict[str, Any]:
    """تقرير موحّد لحالة Phase 3."""
    status = {
        "phase3_enabled": PHASE3_ENABLED,
        "mode": "SHADOW",
        "components": {},
    }

    try:
        from core.phase3.final_brain import get_readiness_report
        status["components"]["final_brain"] = get_readiness_report()
    except Exception as e:
        status["components"]["final_brain"] = {"error": str(e)}

    try:
        from core.phase3.portfolio_brain import get_portfolio_brain_status
        status["components"]["portfolio_brain"] = get_portfolio_brain_status()
    except Exception as e:
        status["components"]["portfolio_brain"] = {"error": str(e)}

    try:
        from core.phase3.ml_safety_framework import get_ml_safety_status
        status["components"]["ml_safety"] = get_ml_safety_status()
    except Exception as e:
        status["components"]["ml_safety"] = {"error": str(e)}

    try:
        from core.phase3.strategy_dna import get_strategy_dna_status
        status["components"]["strategy_dna"] = get_strategy_dna_status()
    except Exception as e:
        status["components"]["strategy_dna"] = {"error": str(e)}

    try:
        from core.phase3.gold_context_layer import get_gold_context_status
        status["components"]["gold_context"] = get_gold_context_status()
    except Exception as e:
        status["components"]["gold_context"] = {"error": str(e)}

    try:
        from core.phase3.adaptive_shadow_calibration import get_adaptive_shadow_status
        status["components"]["adaptive_shadow"] = get_adaptive_shadow_status()
    except Exception as e:
        status["components"]["adaptive_shadow"] = {"error": str(e)}

    return status
