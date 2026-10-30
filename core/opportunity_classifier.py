# =============================================================================
# FER3ON AI V3.5 — OPPORTUNITY QUALITY CLASSIFIER (Phase-2)
# =============================================================================
# Goal: trade with smart density instead of random density. Replaces a binary
# accept/reject decision with a tiered one (GOLD / SILVER / BRONZE / REJECT),
# each carrying its own lot multiplier. This does NOT replace the existing
# hard gates (unified_decision.py hard-block checks, Portfolio Risk Authority,
# quality_score.py gate) — it sits alongside them as an additional, optional
# signal that callers may use to size or further filter a candidate that has
# already cleared the hard gates.
#
# This module makes no MT5 calls and holds no state — pure function, easy to
# unit test and easy to call from any of the independent strategy runners.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.settings import (
    TIER_GOLD_MIN_SCORE,
    TIER_SILVER_MIN_SCORE,
    TIER_BRONZE_MIN_SCORE,
    TIER_REJECT_BELOW,
)

# Session bonus/penalty applied to the composite score before tiering.
# ASIA's -15 reflects the documented 22% WR / 86-trade sample; it is a soft
# signal here, not the hard ASIA_TRADING_ENABLED gate in settings.py/main.py.
_SESSION_BONUS = {
    'LONDON': 8,
    'NEWYORK': 6,
    'OVERLAP': 10,
    'ASIA': -15,
    'OFF_HOURS': -5,
}

_REGIME_BONUS = {
    'TRENDING': 5,
    'EXPLOSIVE': 5,
    'CRISIS': -10,
    'UNKNOWN': -10,
}

_TIER_LOT_MULTIPLIER = {
    'GOLD': 1.00,
    'SILVER': 0.65,
    'BRONZE': 0.30,
    'REJECT': 0.0,
}


@dataclass
class OpportunityTier:
    tier: str               # GOLD | SILVER | BRONZE | REJECT
    lot_multiplier: float   # 1.00 / 0.65 / 0.30 / 0.0
    composite_score: float  # the score that produced this tier, for logging
    notes: list


def classify_opportunity(
    *,
    quality_score: float,
    confidence_pct: float,
    session: str,
    regime: str,
    candle_confirmed: bool = False,
    smc_confirmed: bool = False,
) -> OpportunityTier:
    """
    Classify a trade candidate into GOLD / SILVER / BRONZE / REJECT.

    Inputs mirror what's already computed upstream by quality_score.py,
    confidence_engine.py, session_intelligence.py and market_regime.py — this
    function does not recompute any of those, it only combines them.
    """
    notes = []
    base = float(quality_score or 0) * 0.5 + float(confidence_pct or 0) * 0.3

    if candle_confirmed and smc_confirmed:
        base += 10
        notes.append('CANDLE+SMC_CONFIRMED:+10')

    session_key = str(session or 'UNKNOWN').upper()
    s_bonus = _SESSION_BONUS.get(session_key, 0)
    if s_bonus:
        base += s_bonus
        notes.append(f'SESSION({session_key}):{s_bonus:+d}')

    regime_key = str(regime or 'UNKNOWN').upper()
    r_bonus = _REGIME_BONUS.get(regime_key, 0)
    if r_bonus:
        base += r_bonus
        notes.append(f'REGIME({regime_key}):{r_bonus:+d}')

    base = round(base, 2)

    if base >= TIER_GOLD_MIN_SCORE:
        tier = 'GOLD'
    elif base >= TIER_SILVER_MIN_SCORE:
        tier = 'SILVER'
    elif base >= TIER_BRONZE_MIN_SCORE:
        tier = 'BRONZE'
    else:
        tier = 'REJECT'

    notes.append(f'composite={base} -> {tier}')

    return OpportunityTier(
        tier=tier,
        lot_multiplier=_TIER_LOT_MULTIPLIER[tier],
        composite_score=base,
        notes=notes,
    )
