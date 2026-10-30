# =============================================================================
# FAIE — Market Personality Engine (Phase-2 spec §3.1, new addition)
# =============================================================================
# Different instruments do not deserve identical analyst weighting. XAUUSD
# reacts hard to macro/session liquidity; a range-bound FX pair leans more on
# technical/SMC structure. This module supplies per-symbol overrides for
# EvidenceFusionEngine's weights — it does not change how any analyst reads
# the market, only how much the Chief Decision Officer trusts each analyst's
# voice for a given symbol.
#
# Nothing here executes, sizes, or blocks anything. It is a pure lookup:
# symbol -> weights dict, consumed by ChiefDecisionOfficer(fusion_weights=...).
# =============================================================================

from __future__ import annotations

from typing import Dict

from .fusion import DEFAULT_WEIGHTS

# -----------------------------------------------------------------------
# Per-symbol weight overrides.
#
# Each profile is a FULL replacement weights dict (not a delta) so the
# fusion engine's re-normalization behaves identically to the default case.
# Keys must match analyst names in brain/faie/analysts.py; any analyst name
# omitted from a profile simply gets weight 0 for that symbol (fusion's
# existing re-normalization-over-present-analysts logic already handles
# missing/partial analysts safely, so this is not a special case here).
#
# Rationale for the two profiles below, kept intentionally simple and
# conservative until §6's backtest harness can validate them empirically
# (see PHASE_2_SPECIFICATION.md §3.1 Quality Metric):
#   - XAUUSD: gold trades heavily off macro regime, session liquidity
#     windows (London/NY), and SMC/liquidity-sweep structure; raw candle
#     patterns and psychology notes are historically the weakest signal
#     for this desk's gold strategies, so they are trimmed rather than
#     dropped to zero.
#   - Major FX pairs: comparatively more technical/SMC-driven with less
#     single-asset macro dominance than gold; execution readiness matters
#     slightly more given tighter typical stops.
# Any symbol not listed below falls back to DEFAULT_WEIGHTS unchanged.
# -----------------------------------------------------------------------
PERSONALITY_PROFILES: Dict[str, Dict[str, float]] = {
    "XAUUSD": {
        "MacroAnalyst": 0.12,
        "TechnicalAnalyst": 0.13,
        "SMCAnalyst": 0.18,
        "LiquidityAnalyst": 0.14,
        "VolumeAnalyst": 0.05,
        "PatternAnalyst": 0.06,
        "PsychologyAnalyst": 0.02,
        "RiskOfficer": 0.11,
        "ExecutionOfficer": 0.09,
        # Gold is unusually session-liquidity-sensitive (London/NY open
        # sweeps move it hard) — weighted noticeably higher here than on
        # the FX pairs below.
        "SessionAnalyst": 0.10,
    },
    "EURUSD": {
        "MacroAnalyst": 0.08,
        "TechnicalAnalyst": 0.18,
        "SMCAnalyst": 0.21,
        "LiquidityAnalyst": 0.12,
        "VolumeAnalyst": 0.05,
        "PatternAnalyst": 0.10,
        "PsychologyAnalyst": 0.03,
        "RiskOfficer": 0.09,
        "ExecutionOfficer": 0.08,
        "SessionAnalyst": 0.06,
    },
    "GBPUSD": {
        "MacroAnalyst": 0.09,
        "TechnicalAnalyst": 0.17,
        "SMCAnalyst": 0.20,
        "LiquidityAnalyst": 0.13,
        "VolumeAnalyst": 0.05,
        "PatternAnalyst": 0.09,
        "PsychologyAnalyst": 0.03,
        "RiskOfficer": 0.10,
        "ExecutionOfficer": 0.08,
        # Sterling is heavily a London-hours pair.
        "SessionAnalyst": 0.06,
    },
}


def get_profile(symbol: str) -> Dict[str, float]:
    """Return the fusion-weight profile for `symbol`.

    Failure handling (per spec): an unknown/unrecognized symbol falls back
    to fusion.py's DEFAULT_WEIGHTS unchanged — never raises, never returns
    an empty dict (an empty dict would make EvidenceFusionEngine's
    total_weight collapse to 0, i.e. every decision going flat NEUTRAL).
    """
    key = str(symbol or "").upper().strip()
    profile = PERSONALITY_PROFILES.get(key)
    if not profile:
        return dict(DEFAULT_WEIGHTS)
    return dict(profile)
