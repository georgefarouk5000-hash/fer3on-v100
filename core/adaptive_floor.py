# =============================================================================
# FER3ON AI V3.5 — ADAPTIVE QUALITY FLOOR (Phase-3.2)
# =============================================================================
# IMPORTANT CONTEXT: core/adaptive_learning.py already exists and is already
# live in production (its get_adjusted_thresholds() is read by
# unified_decision.py). It tunes a GLOBAL composite-score threshold from the
# rolling 30-trade win rate. It also tracks per_strategy / per_session /
# per_regime win-rate buckets in its state file — but nothing reads those
# buckets to compute a *per-strategy, per-session* floor.
#
# This module fills exactly that gap. It does NOT duplicate trade recording
# (no new persisted state, no second copy of trade history) — it reads the
# buckets adaptive_learning.py already maintains and derives a floor from
# them. There is deliberately only one place trade outcomes get written:
# adaptive_learning.record_trade_outcome(), already wired into
# core/mt5_history_sync.py.
# =============================================================================

from __future__ import annotations

from typing import Dict

from core.adaptive_learning import load_state
from core.settings import (
    TIER_SILVER_MIN_SCORE,
)

# Per-strategy default floor, used when there isn't enough real data yet.
DEFAULT_FLOORS: Dict[str, float] = {
    'SMC': TIER_SILVER_MIN_SCORE,
    'DAILY': TIER_SILVER_MIN_SCORE,
}

MIN_TRADES_TO_ADAPT = 5     # below this, not enough real data — use default
FLOOR_RELAX_AMOUNT = 5.0    # WR >= 55% in this context -> ease the floor
FLOOR_TIGHTEN_AMOUNT = 10.0  # WR < 35% in this context -> tighten hard
FLOOR_MIN = 40.0
FLOOR_MAX = 85.0


def _bucket_wr(bucket: dict) -> float:
    trades = int(bucket.get('trades', 0) or 0)
    wins = int(bucket.get('wins', 0) or 0)
    if trades <= 0:
        return 0.5
    return wins / trades


def get_adaptive_floor(strategy: str, session: str = 'ANY', regime: str = 'ANY') -> float:
    """
    Returns the minimum quality score to require for `strategy`, informed by
    that strategy's *real* recent win rate (from adaptive_learning's
    per_strategy bucket — not from any backtest).

    This is intentionally conservative: it only ever adjusts based on the
    strategy-level bucket (most data-dense). Session/regime are accepted for
    forward compatibility and logging, but with the trade volumes a personal
    account produces, per_session/per_regime buckets are usually too sparse
    to safely act on alone — mixing them in would just add noise.
    """
    strat = str(strategy or 'UNKNOWN').upper()
    base_floor = DEFAULT_FLOORS.get(strat, TIER_SILVER_MIN_SCORE)

    state = load_state()
    per_strategy = state.get('per_strategy', {})
    bucket = per_strategy.get(strat) or per_strategy.get(strategy) or {}

    trades = int(bucket.get('trades', 0) or 0)
    if trades < MIN_TRADES_TO_ADAPT:
        return base_floor

    wr = _bucket_wr(bucket)
    if wr >= 0.55:
        floor = base_floor - FLOOR_RELAX_AMOUNT
    elif wr < 0.35:
        floor = base_floor + FLOOR_TIGHTEN_AMOUNT
    else:
        floor = base_floor

    return round(max(FLOOR_MIN, min(FLOOR_MAX, floor)), 1)
