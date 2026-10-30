"""Adaptive lot sizing intelligence for controlled exposure."""

from __future__ import annotations

from typing import Any, Dict


def calculate_adaptive_lot(
    balance: float,
    ai_confidence: float,
    volatility: float,
    spread: float,
    drawdown: float,
    session: str,
    market_dna: str,
    orderflow_pressure: float,
    recovery_state: str = "NONE",
    recent_performance: float = 0.5,
    base_lot: float = 0.01,
    execution_decision: str = "FULL_EXECUTION",
    counter_trend: bool = False,
    mtf_lot_multiplier: float = 1.0,
    quant_risk_multiplier: float = 1.0,
) -> float:
    """
    V3.6: أُضيف ``mtf_lot_multiplier`` (اختياري، افتراضي 1.0 — لا يكسر أي
    استدعاء قديم). يأتي من core.trend_confluence.evaluate_mtf_alignment():
      ALIGNED  → 1.00 (لا تغيير)
      NEUTRAL  → 0.75
      CONFLICT → 0.35 (حذر شديد، لكن لا يُصفَّر اللوت أبدًا — لا منع للصفقة)
    يُطبَّق كآخر معامل في السلسلة، فوق كل الحسابات الحالية دون استبدالها.

    V6: أُضيف ``quant_risk_multiplier`` (اختياري، افتراضي 1.0). يأتي من
    analytics.quant_engine.evaluate_strategy_health() — أداء الاستراتيجية
    التاريخي الفعلي (Sharpe/Sortino/Recovery Factor). نطاق
    [QUANT_MIN_RISK_MULTIPLIER, QUANT_MAX_RISK_MULTIPLIER] — لا يصفّر أبدًا.
    """
    balance = max(1.0, float(balance))
    ai_confidence = max(0.0, min(1.0, float(ai_confidence)))
    volatility = max(0.0, float(volatility))
    spread = max(0.0, float(spread))
    drawdown = max(0.0, float(drawdown))
    orderflow_pressure = max(0.0, min(1.0, float(orderflow_pressure)))
    recovery = (recovery_state or "NONE").upper()
    market_dna = (market_dna or "UNKNOWN").upper()
    session = (session or "UNKNOWN").upper()
    mtf_lot_multiplier = max(0.10, min(1.20, float(mtf_lot_multiplier or 1.0)))
    quant_risk_multiplier = max(0.20, min(1.30, float(quant_risk_multiplier or 1.0)))

    raw_lot = base_lot
    session_multiplier = {
        "ASIA": 0.85,
        "LONDON": 1.05,
        "NEW_YORK": 1.10,
        "OVERLAP": 1.12,
        "NEWS_VOLATILITY": 0.75,
        "NEWS": 0.75,
        "SURVIVAL_MODE": 0.60,
        "SURVIVAL": 0.60,
    }.get(session, 1.0)

    if recovery != "NONE":
        raw_lot = base_lot * 0.6
    elif drawdown > 0.08 or volatility > 2.0 or spread > 2.5:
        raw_lot = base_lot * 0.8
    elif market_dna in {"LIQUIDITY_TRAP", "VOLATILITY_EXPANSION", "EXHAUSTION"}:
        raw_lot = base_lot * 0.75
    else:
        growth = (ai_confidence - 0.5) * 0.4 + (recent_performance - 0.5) * 0.15 + (orderflow_pressure - 0.5) * 0.05
        raw_lot = base_lot * (1.0 + max(-0.25, min(0.6, growth)))

    if execution_decision == "MICRO_PROBE":
        raw_lot = min(base_lot * 0.65, 0.02)
    elif execution_decision == "REDUCED_LOT":
        raw_lot = base_lot * 0.70
    elif execution_decision == "SURVIVAL_HOLD":
        raw_lot = base_lot * 0.35

    if counter_trend and raw_lot > 0.02:
        raw_lot = 0.02

    raw_lot *= session_multiplier

    if spread > 3.0:
        raw_lot *= 0.8

    if drawdown > 0.10:
        raw_lot *= 0.7

    # V3.6: MTF Trend Confluence alignment
    raw_lot *= mtf_lot_multiplier

    # V6: Quant Engine strategy health — آخر معامل في السلسلة (أحدث طبقة)
    raw_lot *= quant_risk_multiplier

    max_lot = min(0.25, max(0.01, balance / 20000.0))
    lot = max(0.01, min(max_lot, raw_lot))
    return round(lot, 2)
