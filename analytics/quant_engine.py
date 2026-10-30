# =============================================================================
# FER3ON V6 — QUANT ENGINE
# =============================================================================
# الفلسفة:
#   يُكمِّل analytics/truth_layer.py (Win Rate, Profit Factor, Expectancy,
#   Max Drawdown — موجودة مسبقًا) بثلاث مقاييس إحصائية متقدمة غير موجودة:
#   Sharpe Ratio, Sortino Ratio, Recovery Factor — ثم يترجمها إلى توصية
#   risk_multiplier فعلية لكل استراتيجية على حدة.
#
#   القرار المنهجي الصريح: Sharpe/Sortino التقليديان يُحسبان على عوائد
#   دورية (يومية/شهرية) لمحفظة مستمرة. في EA بصفقات متفرقة بدون جدولة
#   زمنية ثابتة، المنهج المعتمد في صناعة التداول الخوارزمي هو حسابهما على
#   توزيع "per-trade returns" (نفس منهج compute_metrics الحالي في
#   truth_layer.py) — هذا يُعطي قياسًا متسقًا مع باقي مقاييس المشروع، لكنه
#   ليس مطابقًا حرفيًا لـ Sharpe السنوي التقليدي لصندوق استثمار. القيم هنا
#   تُفسَّر نسبيًا (مقارنة استراتيجية بأخرى، أو الاستراتيجية بنفسها بمرور
#   الوقت) لا كأرقام معيارية مطلقة من الأسواق التقليدية.
#
#   RUNTIME INFLUENCE: بعكس Phase 2 (PHASE2_RUNTIME_INFLUENCE=False بتصميم
#   متعمد)، هذا الموديول V6 لـه تأثير فعلي على وقت التشغيل عبر
#   evaluate_strategy_health() → risk_multiplier يُستهلك من
#   core/unified_decision.py + core/adaptive_lot_engine.py. التعطيل التام
#   غير مسموح أبدًا (نفس فلسفة "لا حظر، فقط تصغير" المتفقة عليها سابقًا)؛
#   الحد الأدنى المطلق QUANT_MIN_RISK_MULTIPLIER يضمن هذا دائمًا.
# =============================================================================

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from analytics.truth_layer import TradeRecord, load_all_trades, filter_trades, compute_metrics
from core.settings import (
    BASE_ACCOUNT_BALANCE,
    QUANT_MIN_TRADES_FOR_HEALTH,
    QUANT_MIN_RISK_MULTIPLIER,
    QUANT_MAX_RISK_MULTIPLIER,
    QUANT_HEALTH_THRESHOLDS,
    BUILD_ID,
)


# =============================================================================
# ADVANCED RISK-ADJUSTED METRICS
# =============================================================================

@dataclass
class AdvancedMetrics:
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    recovery_factor: float = 0.0
    sample_size: int = 0
    mean_return: float = 0.0
    std_return: float = 0.0
    downside_std: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _per_trade_returns(trades: List[TradeRecord]) -> List[float]:
    """عائد كل صفقة كنسبة من رأس المال الأساسي (موحّد عبر الاستراتيجيات)."""
    base = float(BASE_ACCOUNT_BALANCE) or 1.0
    return [float(t.profit or 0.0) / base for t in trades]


def compute_advanced_metrics(trades: List[TradeRecord]) -> AdvancedMetrics:
    """
    يحسب Sharpe, Sortino, Recovery Factor من سجل صفقات فعلي (Truth Layer).
    يُرجع قيم صفرية مع `note` توضيحية لو العيّنة صغيرة جدًا للدلالة الإحصائية
    (لا يُخمِّن أو يَستنتج من عيّنة غير كافية).
    """
    n = len(trades)
    if n < 2:
        return AdvancedMetrics(sample_size=n, note="INSUFFICIENT_SAMPLE_MIN_2")

    returns = _per_trade_returns(trades)
    mean_r = sum(returns) / n

    variance = sum((r - mean_r) ** 2 for r in returns) / n
    std_r = math.sqrt(variance)

    downside_returns = [min(0.0, r) for r in returns]
    downside_variance = sum(r ** 2 for r in downside_returns) / n
    downside_std = math.sqrt(downside_variance)

    sharpe = (mean_r / std_r) if std_r > 1e-12 else 0.0
    sortino = (mean_r / downside_std) if downside_std > 1e-12 else 0.0

    # Recovery Factor = صافي الربح / أقصى Drawdown (من نفس منهج truth_layer)
    m = compute_metrics(trades)
    recovery = (m.net_pnl / m.max_drawdown) if m.max_drawdown > 1e-9 else (
        float("inf") if m.net_pnl > 0 else 0.0
    )
    # تطبيع: نتجنّب "inf" في الإخراج لمنع كسر أي تجميع/تسلسل JSON لاحق
    if recovery == float("inf"):
        recovery = 999.0

    note = "" if n >= QUANT_MIN_TRADES_FOR_HEALTH else (
        f"LOW_SAMPLE_SIZE_{n}_BELOW_RECOMMENDED_{QUANT_MIN_TRADES_FOR_HEALTH}"
    )

    return AdvancedMetrics(
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        recovery_factor=round(recovery, 4),
        sample_size=n,
        mean_return=round(mean_r, 6),
        std_return=round(std_r, 6),
        downside_std=round(downside_std, 6),
        note=note,
    )


# =============================================================================
# STRATEGY HEALTH — التكيّف الفعلي (Runtime Influence)
# =============================================================================

@dataclass
class StrategyHealth:
    strategy: str
    health_tier: str           # EXCELLENT | GOOD | NEUTRAL | WEAK | POOR | UNKNOWN
    risk_multiplier: float     # يُستهلك فعليًا من unified_decision/adaptive_lot_engine
    sample_size: int
    metrics: Dict[str, Any]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _classify_health(
    win_rate: float,
    profit_factor: float,
    sharpe: float,
    sample_size: int,
) -> str:
    """
    تصنيف صحة الاستراتيجية حسب عتبات قابلة للتعديل (core/settings.py
    QUANT_HEALTH_THRESHOLDS) — لا قيم صلبة مدفونة في الكود.
    """
    if sample_size < QUANT_MIN_TRADES_FOR_HEALTH:
        return "UNKNOWN"

    t = QUANT_HEALTH_THRESHOLDS

    if profit_factor >= t["excellent_pf"] and sharpe >= t["excellent_sharpe"]:
        return "EXCELLENT"
    if profit_factor >= t["good_pf"] and sharpe >= t["good_sharpe"]:
        return "GOOD"
    if profit_factor >= t["neutral_pf"]:
        return "NEUTRAL"
    if profit_factor >= t["weak_pf"]:
        return "WEAK"
    return "POOR"


def evaluate_strategy_health(strategy: str, trades: Optional[List[TradeRecord]] = None) -> StrategyHealth:
    """
    الدالة الرئيسية المُستهلكة من core/trade_executor.py (نقطة الالتقاء
    الفعلية لمسارات فتح الصفقات — انظر التوثيق في core/trade_executor.py.
    تُرجع risk_multiplier فعليًا قابلاً للاستخدام مباشرة — مطابق تمامًا لنمط
    mtf_lot_multiplier (V3.6): لا يصفّر أبدًا (QUANT_MIN_RISK_MULTIPLIER
    كحد أدنى مطلق)، فقط يُحجّم.

    NOTE — PERFORMANCE AT SCALE: تُستدعى حاليًا مرة واحدة قبل كل صفقة
    جديدة (داخل execute_trade)، وتقرأ load_all_trades() من القرص كل مرة
    (~0.1ms حاليًا مع سجل صغير). مع تراكم آلاف الصفقات بمرور الوقت سيتباطأ
    القراءة المتكررة من القرص تدريجيًا. لم يُضَف caching بعد — لو أصبح هذا
    عنق زجاجة فعليًا (يُقاس، لا يُخمَّن)، الحل المقترح: تخزين مؤقت بفاصل
    زمني (مثلاً تحديث كل N دقيقة بدل كل صفقة) بدل قراءة القرص في كل نداء.

    Parameters
    ----------
    strategy : active strategy name
    trades   : قائمة صفقات اختيارية (لو غير مُمررة، تُحمَّل من Truth Layer)
    """
    strat = str(strategy or "").upper()

    if trades is None:
        all_trades = load_all_trades()
        # DATA-INTEGRITY FIX: previously filter_trades(all_trades,
        # strategy=strat) blended retired pre-merge strategy trades in with
        # this build's real trades -- e.g. logged as "QUANT_HEALTH | SMC |
        # tier=POOR | n=82" during burn-in, when this build only had ~20-30
        # real SMC trades at the time. That POOR/n=82 verdict was silently
        # cutting real position sizes (QUANT_LOT_ADJUST ×0.3) and scoring
        # penalties (unified_decision.py QUANT_HEALTH_WEAK) based on a
        # blend that included a strategy version that no longer runs.
        trades = filter_trades(all_trades, strategy=strat, build_id=BUILD_ID)

    n = len(trades)

    if n < QUANT_MIN_TRADES_FOR_HEALTH:
        # عيّنة غير كافية للحكم — لا عقوبة ولا بونص، نتركها على وضعها الطبيعي
        # (هذا ليس "تعطيل تأثير" بل غياب دليل كافٍ، فلسفيًا مختلف عن الحظر)
        return StrategyHealth(
            strategy=strat, health_tier="UNKNOWN", risk_multiplier=1.0,
            sample_size=n, metrics={},
            reason=f"SAMPLE_TOO_SMALL_{n}_OF_{QUANT_MIN_TRADES_FOR_HEALTH}_NEUTRAL_DEFAULT",
        )

    base_metrics = compute_metrics(trades)
    adv_metrics = compute_advanced_metrics(trades)

    tier = _classify_health(
        win_rate=base_metrics.win_rate,
        profit_factor=base_metrics.profit_factor if base_metrics.profit_factor != float("inf") else 999.0,
        sharpe=adv_metrics.sharpe_ratio,
        sample_size=n,
    )

    risk_mult_by_tier = {
        "EXCELLENT": QUANT_MAX_RISK_MULTIPLIER,
        "GOOD": 1.10,
        "NEUTRAL": 1.0,
        "WEAK": 0.65,
        "POOR": QUANT_MIN_RISK_MULTIPLIER,
        "UNKNOWN": 1.0,
    }
    risk_multiplier = max(
        QUANT_MIN_RISK_MULTIPLIER,
        min(QUANT_MAX_RISK_MULTIPLIER, risk_mult_by_tier.get(tier, 1.0)),
    )

    log_line = (
        f"📊 QUANT_HEALTH | {strat} | tier={tier} | n={n}"
        f" | win_rate={base_metrics.win_rate:.2f} pf={base_metrics.profit_factor:.2f}"
        f" sharpe={adv_metrics.sharpe_ratio:.3f} sortino={adv_metrics.sortino_ratio:.3f}"
        f" recovery={adv_metrics.recovery_factor:.2f}"
        f" → risk_multiplier={risk_multiplier:.2f}"
    )
    print(log_line)

    return StrategyHealth(
        strategy=strat,
        health_tier=tier,
        risk_multiplier=round(risk_multiplier, 3),
        sample_size=n,
        metrics={**base_metrics.to_dict(), **adv_metrics.to_dict()},
        reason=f"{tier}_TIER_FROM_{n}_TRADES",
    )


def evaluate_all_strategies_health(
    strategies: Optional[List[str]] = None,
) -> Dict[str, StrategyHealth]:
    """يُرجع StrategyHealth لكل استراتيجية — يُستخدم من dashboard/تقارير دورية."""
    strategies = strategies or ["SMC", "DAILY"]
    all_trades = load_all_trades()
    out: Dict[str, StrategyHealth] = {}
    for strat in strategies:
        strat_trades = filter_trades(all_trades, strategy=strat)
        out[strat] = evaluate_strategy_health(strat, trades=strat_trades)
    return out
