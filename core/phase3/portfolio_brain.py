# =============================================================================
# FER3ON — PHASE 3 | PORTFOLIO_BRAIN (Shadow Mode)
# =============================================================================
# الدور: ذكاء تخصيص رأس المال والانكشاف على مستوى المحفظة.
# الوضع الحالي: SHADOW ONLY — يُغذّي FINAL_BRAIN بمعلومات مؤسسية.
#
# يعمل فوق portfolio_risk_authority الحالي ولا يستبدله.
# البنية: portfolio_risk_authority (موجود) → PORTFOLIO_BRAIN (جديد، additive)
#
# المخرجات للـ FINAL_BRAIN:
#   - exposure_score: درجة الانكشاف الحالية (0-100)
#   - strategy_allocation_bias: انحياز التخصيص للاستراتيجيات
#   - capital_pressure: ضغط رأس المال
#   - diversification_state: حالة التنويع
#
# ما لا يفعله الآن:
#   - لا يرفض صفقات مباشرة
#   - لا يستبدل portfolio_risk_authority
#   - لا يغيّر قواعد BUY/SELL
# =============================================================================

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.settings import (
    BASE_ACCOUNT_BALANCE,
    MAX_OPEN_TRADES,
    PHASE3_PORTFOLIO_BRAIN_DIR,
    PORTFOLIO_BRAIN_CAPITAL_PRESSURE_WARN,
    PORTFOLIO_BRAIN_DIVERSITY_TARGET,
    PORTFOLIO_BRAIN_ENABLED,
    PORTFOLIO_BRAIN_LIVE_AUTHORITY,
    PORTFOLIO_BRAIN_MAX_EXPOSURE_PCT,
    PORTFOLIO_BRAIN_SHADOW_LOG,
    PORTFOLIO_BRAIN_STRATEGY_WEIGHTS,
)

_STATE_FILE = os.path.join(PHASE3_PORTFOLIO_BRAIN_DIR, "portfolio_brain_state.json")
_SHADOW_LOG_FILE = os.path.join(PHASE3_PORTFOLIO_BRAIN_DIR, "shadow_portfolio.jsonl")

assert not PORTFOLIO_BRAIN_LIVE_AUTHORITY, (
    "PORTFOLIO_BRAIN: Live authority is disabled in Phase 3. "
    "Enable only after completing shadow validation."
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PortfolioBrainSnapshot:
    """لقطة حالة المحفظة من منظور مؤسسي."""
    open_trades_count: int = 0
    open_strategies: List[str] = field(default_factory=list)
    total_exposure_pct: float = 0.0
    strategy_distribution: Dict[str, int] = field(default_factory=dict)
    capital_used_pct: float = 0.0
    account_balance: float = BASE_ACCOUNT_BALANCE
    timestamp: float = field(default_factory=time.time)


@dataclass
class PortfolioBrainOutput:
    """مخرجات PORTFOLIO_BRAIN لـ FINAL_BRAIN."""
    exposure_score: float = 50.0        # 0=انكشاف كامل, 100=مساحة كافية
    strategy_allocation_bias: Dict[str, float] = field(default_factory=dict)
    capital_pressure: float = 0.0      # 0=لا ضغط, 100=ضغط كامل
    diversification_state: str = "BALANCED"  # BALANCED / CONCENTRATED / SPARSE
    portfolio_brain_score: float = 50.0  # الدرجة المركّبة لـ FINAL_BRAIN
    warnings: List[str] = field(default_factory=list)
    mode: str = "SHADOW"
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# CORE LOGIC
# =============================================================================

def _ensure_dirs() -> None:
    os.makedirs(PHASE3_PORTFOLIO_BRAIN_DIR, exist_ok=True)


def _compute_exposure_score(snapshot: PortfolioBrainSnapshot) -> float:
    """
    درجة الانكشاف: 100 = مساحة كاملة متاحة، 0 = محفظة مشبعة.
    """
    if MAX_OPEN_TRADES == 0:
        return 100.0
    utilization = snapshot.open_trades_count / MAX_OPEN_TRADES
    # إضافة تأثير نسبة الانكشاف بالرأس المال
    exposure_factor = min(1.0, snapshot.total_exposure_pct / PORTFOLIO_BRAIN_MAX_EXPOSURE_PCT)
    combined = (utilization * 0.6 + exposure_factor * 0.4)
    return round(max(0.0, 100.0 - (combined * 100)), 2)


def _compute_capital_pressure(snapshot: PortfolioBrainSnapshot) -> float:
    """ضغط رأس المال: 0 = لا ضغط، 100 = ضغط كامل."""
    pressure = (snapshot.capital_used_pct / 100.0) * 100.0
    return round(min(100.0, max(0.0, pressure)), 2)


def _compute_diversification_state(snapshot: PortfolioBrainSnapshot) -> str:
    """تقييم حالة التنويع."""
    unique_strategies = len(set(snapshot.open_strategies))
    if unique_strategies == 0:
        return "EMPTY"
    elif unique_strategies >= PORTFOLIO_BRAIN_DIVERSITY_TARGET:
        return "BALANCED"
    elif unique_strategies == 1 and snapshot.open_trades_count > 2:
        return "CONCENTRATED"
    else:
        return "SPARSE"


def _compute_strategy_allocation_bias(
    snapshot: PortfolioBrainSnapshot,
) -> Dict[str, float]:
    """
    حساب انحياز التخصيص: الفرق بين الأوزان المستهدفة والتوزيع الفعلي.
    قيمة موجبة = ينبغي إضافة المزيد من هذه الاستراتيجية.
    قيمة سلبية = هذه الاستراتيجية ممثَّلة بشكل زائد.
    """
    total = max(1, snapshot.open_trades_count)
    bias = {}
    for strategy, target_weight in PORTFOLIO_BRAIN_STRATEGY_WEIGHTS.items():
        actual_count = snapshot.strategy_distribution.get(strategy, 0)
        actual_weight = actual_count / total
        bias[strategy] = round(target_weight - actual_weight, 4)
    return bias


def _compute_portfolio_brain_score(
    exposure_score: float,
    capital_pressure: float,
    diversification_state: str,
) -> float:
    """درجة مركّبة للـ FINAL_BRAIN."""
    diversity_bonus = {
        "BALANCED": 10.0,
        "SPARSE": 5.0,
        "CONCENTRATED": -5.0,
        "EMPTY": 0.0,
    }.get(diversification_state, 0.0)

    score = (
        exposure_score * 0.50
        + (100 - capital_pressure) * 0.40
        + (50 + diversity_bonus) * 0.10
    )
    return round(min(100.0, max(0.0, score)), 2)


# =============================================================================
# PUBLIC API
# =============================================================================

def evaluate_portfolio_shadow(
    open_trades: Optional[List[Dict[str, Any]]] = None,
    account_balance: float = BASE_ACCOUNT_BALANCE,
    equity: float = BASE_ACCOUNT_BALANCE,
    candidate_id: Optional[str] = None,
) -> PortfolioBrainOutput:
    """
    التقييم الرئيسي لـ PORTFOLIO_BRAIN في وضع Shadow.
    يُستدعى قبل FINAL_BRAIN لتزويده بدرجة المحفظة.
    """
    if not PORTFOLIO_BRAIN_ENABLED:
        return PortfolioBrainOutput(
            portfolio_brain_score=50.0,
            mode="DISABLED",
        )

    open_trades = open_trades or []
    open_strategies = [t.get("strategy", "UNKNOWN") for t in open_trades]
    strategy_distribution: Dict[str, int] = {}
    for s in open_strategies:
        strategy_distribution[s] = strategy_distribution.get(s, 0) + 1

    total_exposure_pct = 0.0
    for t in open_trades:
        lot = t.get("lot", 0.0)
        risk_pct = t.get("risk_pct", 0.75)
        total_exposure_pct += risk_pct

    capital_used_pct = max(0.0, min(100.0, (1 - equity / max(1, account_balance)) * 100))

    snapshot = PortfolioBrainSnapshot(
        open_trades_count=len(open_trades),
        open_strategies=open_strategies,
        total_exposure_pct=total_exposure_pct,
        strategy_distribution=strategy_distribution,
        capital_used_pct=capital_used_pct,
        account_balance=account_balance,
    )

    exposure_score = _compute_exposure_score(snapshot)
    capital_pressure = _compute_capital_pressure(snapshot)
    diversification_state = _compute_diversification_state(snapshot)
    allocation_bias = _compute_strategy_allocation_bias(snapshot)
    portfolio_score = _compute_portfolio_brain_score(
        exposure_score, capital_pressure, diversification_state
    )

    warnings = []
    if capital_pressure >= PORTFOLIO_BRAIN_CAPITAL_PRESSURE_WARN * 100:
        warnings.append(f"Capital pressure high: {capital_pressure:.1f}%")
    if diversification_state == "CONCENTRATED":
        warnings.append("Portfolio concentrated in single strategy")
    if exposure_score < 20:
        warnings.append("Portfolio near capacity — exposure score low")

    output = PortfolioBrainOutput(
        exposure_score=exposure_score,
        strategy_allocation_bias=allocation_bias,
        capital_pressure=capital_pressure,
        diversification_state=diversification_state,
        portfolio_brain_score=portfolio_score,
        warnings=warnings,
        mode="SHADOW",
    )

    if PORTFOLIO_BRAIN_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate_id,
            "snapshot": asdict(snapshot),
            "output": asdict(output),
        }
        try:
            from core.trade_event_ledger import append_candidate_record
            append_candidate_record(_SHADOW_LOG_FILE, record)
        except Exception as e:
            print(f"[PORTFOLIO_BRAIN] Log error: {e}")

    if warnings:
        print(f"[PORTFOLIO_BRAIN SHADOW] ⚠ {' | '.join(warnings)}")

    print(
        f"[PORTFOLIO_BRAIN SHADOW] Score={portfolio_score:.1f} | "
        f"Exposure={exposure_score:.1f} | Pressure={capital_pressure:.1f} | "
        f"Diversity={diversification_state} | OpenTrades={len(open_trades)}"
    )

    return output


def get_portfolio_brain_status() -> Dict[str, Any]:
    """تقرير حالة PORTFOLIO_BRAIN."""
    return {
        "component": "PORTFOLIO_BRAIN",
        "mode": "SHADOW",
        "enabled": PORTFOLIO_BRAIN_ENABLED,
        "live_authority": PORTFOLIO_BRAIN_LIVE_AUTHORITY,
        "strategy_weights": PORTFOLIO_BRAIN_STRATEGY_WEIGHTS,
        "max_exposure_pct": PORTFOLIO_BRAIN_MAX_EXPOSURE_PCT,
        "diversity_target": PORTFOLIO_BRAIN_DIVERSITY_TARGET,
        "capital_pressure_warn": PORTFOLIO_BRAIN_CAPITAL_PRESSURE_WARN,
    }
