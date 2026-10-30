# =========================================
# FER3ON V3.0 — CANDLE INTELLIGENCE GATE
# Spec: FER3ON Candle Intelligence Engine V3.0
# Role: Execution timing improver — NOT decision authority
# =========================================
#
# PHILOSOPHY (from spec):
#   Candles are Execution Intelligence Components.
#   Candles do NOT become a strategy.
#   Candles can never be Single Decision Authority.
#
# INTEGRATION:
#   Called from candle_trigger.check_candle_trigger() after
#   M5/M15 pattern analysis.  Returns a composite dict that
#   the caller merges into its existing AggregateResult.
#
# OUTPUT KEY:
#   candle_bonus     — added to base_score   (0 … +6)
#   candle_penalty   — subtracted from score  (0 … +8)
#   hard_warning     — True when opposite ≥ 95 + Tier-A
#   hard_block       — True only when ALL four block conditions met
#   mtf_bonus        — MTF alignment bonus (0, +1, +2, +4)
#   composite_delta  — candle_bonus − candle_penalty + mtf_bonus
#   log_line         — structured log string matching spec format
# =========================================

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# =========================================
# CONSTANTS — directly from spec
# =========================================

# Tier A: Major Reversal  (weight 5)
_TIER_A: frozenset = frozenset({
    "ENGULFING_BULLISH",
    "ENGULFING_BEARISH",
    "THREE_WHITE_SOLDIERS",
    "THREE_BLACK_CROWS",
    # internal pattern name variants used by candle_engine / candle_patterns
    "ENGULFING",
})

# Tier B: Strong Confirmation  (weight 4)
_TIER_B: frozenset = frozenset({
    "PINBAR_BUY",
    "PINBAR_SELL",
    "REJECTION_BUY",
    "REJECTION_SELL",
    "SHOOTING_STAR",
    "HAMMER",
    # internal alias
    "PIN_BAR",
    "REJECTION",
})

# Tier C: Minor Confirmation  (weight 2)
_TIER_C: frozenset = frozenset({
    "INSIDE_BAR",
    "INSIDE_BAR_BREAKOUT",
    "MOMENTUM_BREAKOUT",
    "MORNING_STAR",
    "EVENING_STAR",
})

# Tier weights
_TIER_WEIGHT: Dict[str, int] = {}
for _p in _TIER_A:
    _TIER_WEIGHT[_p] = 5
for _p in _TIER_B:
    _TIER_WEIGHT[_p] = 4
for _p in _TIER_C:
    _TIER_WEIGHT[_p] = 2

# Strength → multiplier table  (≥ threshold → multiplier)
_STRENGTH_MULTIPLIERS: Tuple[Tuple[int, float], ...] = (
    (90, 1.30),
    (80, 1.15),
    (70, 1.00),
    (60, 0.80),
    (0,  0.50),   # < 60
)

# Opposite candle penalty table  (≥ threshold → penalty)
_OPPOSITE_PENALTIES: Tuple[Tuple[int, int], ...] = (
    (95, 8),
    (85, 5),
    (75, 4),
    (65, 3),
    (55, 2),
    (0,  1),
)

# MTF bonus values
_MTF_M5_ONLY   = 2
_MTF_M15_ONLY  = 1
_MTF_BOTH      = 4   # M5 + M15 aligned → +4 (overrides individual)

# Max candle bonus contribution
_MAX_BONUS = 6


# =========================================
# HELPERS
# =========================================

def _strength_multiplier(strength: float) -> float:
    """Return spec multiplier for a given candle strength (0-100)."""
    s = float(strength or 0)
    for threshold, mult in _STRENGTH_MULTIPLIERS:
        if s >= threshold:
            return mult
    return 0.50


def _pattern_tier_weight(pattern_name: str) -> int:
    """Return the spec tier weight for a pattern name (0 if unknown)."""
    name = str(pattern_name or "").upper().strip()
    if name in _TIER_WEIGHT:
        return _TIER_WEIGHT[name]
    # Partial-match fallbacks for variant names
    if "ENGULF" in name:
        return 5
    if "THREE_WHITE" in name or "THREE_BLACK" in name:
        return 5
    if "PIN" in name or "PINBAR" in name:
        return 4
    if "REJECTION" in name or "SHOOTING" in name or "HAMMER" in name:
        return 4
    if "INSIDE" in name or "MOMENTUM" in name or "MORNING" in name or "EVENING" in name:
        return 2
    return 0


def _is_tier_a(pattern_name: str) -> bool:
    name = str(pattern_name or "").upper()
    if name in _TIER_A:
        return True
    return "ENGULF" in name or "THREE_WHITE" in name or "THREE_BLACK" in name


def _opposite_penalty(strength: float) -> Tuple[int, bool]:
    """Return (penalty_points, hard_warning_flag) for an opposing candle."""
    s = float(strength or 0)
    hard_warning = s >= 95
    for threshold, penalty in _OPPOSITE_PENALTIES:
        if s >= threshold:
            return penalty, hard_warning
    return 1, False


# =========================================
# CLOSED-CANDLE GUARD
# =========================================

class _ClosedCandleState:
    """Per-symbol duplicate-processing guard (module-level singleton)."""

    _registry: Dict[str, Any] = {}

    @classmethod
    def is_duplicate(cls, symbol: str, tf: str, candle_time: Any) -> bool:
        key = f"{symbol}:{tf}"
        if cls._registry.get(key) == candle_time:
            return True
        cls._registry[key] = candle_time
        return False


def get_closed_candle(rates, symbol: str = "", tf: str = "M5"):
    """
    Return the last CLOSED candle (iloc[-2] equivalent) and check
    for duplicate processing.

    Returns (candle_dict, is_duplicate).
    """
    if rates is None or len(rates) < 2:
        return None, True

    # Support both numpy structured arrays and plain dicts
    try:
        closed = rates[-2]
        if hasattr(closed, "tolist"):
            closed = dict(zip(closed.dtype.names, closed.tolist()))
        elif not isinstance(closed, dict):
            closed = {
                "open":  float(closed[0]),
                "high":  float(closed[1]),
                "low":   float(closed[2]),
                "close": float(closed[3]),
                "time":  None,
            }
    except Exception:
        return None, True

    candle_time = closed.get("time")
    is_dup = _ClosedCandleState.is_duplicate(symbol, tf, candle_time)
    return closed, is_dup


# =========================================
# BONUS ENGINE
# =========================================

def compute_candle_bonus(pattern_name: str, strength: float) -> float:
    """
    Compute aligning-candle bonus.

    bonus = tier_weight * strength_multiplier
    Capped at MAX_BONUS (+6).
    """
    weight = _pattern_tier_weight(pattern_name)
    if weight == 0:
        return 0.0
    mult = _strength_multiplier(strength)
    bonus = weight * mult
    return min(round(bonus, 2), _MAX_BONUS)


# =========================================
# OPPOSITE CANDLE ENGINE
# =========================================

def compute_opposite_penalty(pattern_name: str, strength: float) -> Tuple[float, bool]:
    """
    Compute penalty for a candle that opposes the intended trade direction.

    Returns (penalty, hard_warning).
    hard_warning is True when strength ≥ 95.
    """
    if not pattern_name or pattern_name in ("NONE", ""):
        return 0.0, False
    penalty, hard_warning = _opposite_penalty(strength)
    return float(penalty), hard_warning


# =========================================
# MTF ALIGNMENT ENGINE
# =========================================

def compute_mtf_bonus(
    signal: str,
    m5_direction: str,
    m15_direction: str,
) -> Tuple[int, bool, str]:
    """
    Compute MTF candle alignment bonus.

    Rules (spec):
      M5 + M15 aligned  → +4
      M5 only aligned   → +2
      M15 only aligned  → +1
      M5 opposite       → apply penalty (handled by caller via opposite engine)
      Never auto-reject from MTF alone.

    Returns (bonus, m5_opposite, reason_str).
    """
    sig = str(signal or "").upper()
    m5  = str(m5_direction  or "NONE").upper()
    m15 = str(m15_direction or "NONE").upper()

    m5_aligned  = m5 == sig and m5 != "NONE"
    m15_aligned = m15 == sig and m15 != "NONE"
    m5_opposite = m5 not in ("NONE", sig) and m5 != "NONE"

    if m5_aligned and m15_aligned:
        return _MTF_BOTH, False, "MTF_M5+M15_ALIGNED"
    if m5_aligned:
        return _MTF_M5_ONLY, False, "MTF_M5_ALIGNED"
    if m15_aligned:
        return _MTF_M15_ONLY, m5_opposite, "MTF_M15_ALIGNED"
    if m5_opposite:
        return 0, True, "MTF_M5_OPPOSITE"
    return 0, False, "MTF_NEUTRAL"


# =========================================
# HARD BLOCK CONDITIONS
# =========================================

def evaluate_hard_block(
    opposite_strength: float,
    opposite_pattern: str,
    mtf_aligned: bool,
    structure_confidence: float,
) -> bool:
    """
    Hard block ONLY when ALL four conditions are true (spec):
      1. Opposite candle strength ≥ 95
      2. Opposite pattern is Tier A
      3. MTF alignment = False
      4. Structure confidence < 70

    Returns True → hard block (reject entry).
    """
    cond_1 = float(opposite_strength or 0) >= 95
    cond_2 = _is_tier_a(opposite_pattern)
    cond_3 = not bool(mtf_aligned)
    cond_4 = float(structure_confidence or 100) < 70
    return cond_1 and cond_2 and cond_3 and cond_4


# =========================================
# COMPOSITE GATE — MAIN ENTRY POINT
# =========================================

def evaluate_candle_gate(
    signal: str,
    m5_pattern:   str,
    m5_direction: str,
    m5_strength:  float,
    m15_pattern:  str,
    m15_direction: str,
    m15_strength:  float,
    base_score:   float = 0.0,
    structure_confidence: float = 100.0,
    closed_m5_time: Any = None,
    closed_m15_time: Any = None,
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Full V3.0 gate evaluation.

    Parameters
    ----------
    signal            : "BUY" | "SELL"
    m5_pattern        : pattern name from M5 analysis
    m5_direction      : direction from M5 analysis
    m5_strength       : strength 0-100 from M5 analysis
    m15_pattern       : pattern name from M15 analysis
    m15_direction     : direction from M15 analysis
    m15_strength      : strength 0-100 from M15 analysis
    base_score        : existing composite score before candle adjustment
    structure_confidence : SMC/structure confidence for hard-block check
    closed_m5_time    : time field of the closed M5 candle (dedup guard)
    closed_m15_time   : time field of the closed M15 candle (dedup guard)
    symbol            : instrument symbol (used in dedup guard)

    Returns
    -------
    dict with keys:
        candle_bonus        float   — alignment bonus (0…+6)
        candle_penalty      float   — opposition penalty (0…+8)
        hard_warning        bool    — extreme opposite signal flag
        hard_block          bool    — full rejection flag
        mtf_bonus           int     — MTF alignment bonus (0,1,2,4)
        mtf_reason          str     — human-readable MTF result
        composite_delta     float   — net score change
        final_score         float   — base_score + composite_delta
        execution_mode      str     — FULL_ENTRY / REDUCED / BLOCKED / NEUTRAL
        aligned             bool    — at least one TF aligned with signal
        log_line            str     — 🕯 CANDLE_ENGINE structured log
    """
    sig = str(signal or "").upper()

    # ── Duplicate guard (closed-candle rule) ──────────────────────────
    m5_dup  = _ClosedCandleState.is_duplicate(symbol, "M5",  closed_m5_time)
    m15_dup = _ClosedCandleState.is_duplicate(symbol, "M15", closed_m15_time)
    # Note: we don't block processing just because it's duplicate here —
    # the caller can decide; we include the flags in the result for logging.

    # ── Classify each TF as aligning, opposing, or neutral ───────────
    m5_pat  = str(m5_pattern  or "NONE").upper()
    m15_pat = str(m15_pattern or "NONE").upper()
    m5_dir  = str(m5_direction  or "NONE").upper()
    m15_dir = str(m15_direction or "NONE").upper()
    m5_str  = float(m5_strength  or 0)
    m15_str = float(m15_strength or 0)

    m5_aligned  = m5_dir  == sig and m5_dir  != "NONE" and m5_pat  != "NONE"
    m15_aligned = m15_dir == sig and m15_dir != "NONE" and m15_pat != "NONE"
    m5_opposite = m5_dir  not in ("NONE", sig) and m5_dir  != "NONE" and m5_pat  != "NONE"
    m15_opposite= m15_dir not in ("NONE", sig) and m15_dir != "NONE" and m15_pat != "NONE"

    # ── Candle Bonus (aligning candles) ──────────────────────────────
    bonus_m5  = compute_candle_bonus(m5_pat,  m5_str)  if m5_aligned  else 0.0
    bonus_m15 = compute_candle_bonus(m15_pat, m15_str) if m15_aligned else 0.0
    # Spec: max total contribution = +6
    candle_bonus = min(bonus_m5 + bonus_m15, _MAX_BONUS)

    # ── Opposite Candle Penalty ───────────────────────────────────────
    # Primary opposing TF: M5 carries more weight in execution timeframe
    hard_warning = False
    candle_penalty = 0.0

    if m5_opposite:
        pen, hw = compute_opposite_penalty(m5_pat, m5_str)
        candle_penalty = max(candle_penalty, pen)
        hard_warning   = hard_warning or hw

    if m15_opposite:
        pen, hw = compute_opposite_penalty(m15_pat, m15_str)
        # M15 opposing is secondary — apply at 60% weight
        candle_penalty = max(candle_penalty, round(pen * 0.6, 1))
        hard_warning   = hard_warning or hw

    # ── MTF Alignment Bonus ──────────────────────────────────────────
    mtf_bonus, m5_opp_flag, mtf_reason = compute_mtf_bonus(sig, m5_dir, m15_dir)

    # ── Hard Block Check ─────────────────────────────────────────────
    # Use the strongest opposing pattern/strength for the check
    opp_pat = m5_pat if m5_opposite else (m15_pat if m15_opposite else "NONE")
    opp_str = m5_str if m5_opposite else (m15_str if m15_opposite else 0.0)
    mtf_any_aligned = m5_aligned or m15_aligned

    hard_block = evaluate_hard_block(
        opposite_strength    = opp_str,
        opposite_pattern     = opp_pat,
        mtf_aligned          = mtf_any_aligned,
        structure_confidence = structure_confidence,
    )

    # ── Composite Delta & Final Score ────────────────────────────────
    composite_delta = candle_bonus - candle_penalty + mtf_bonus
    final_score     = round(float(base_score or 0) + composite_delta, 2)

    # ── Execution Mode ───────────────────────────────────────────────
    if hard_block:
        execution_mode = "BLOCKED"
    elif hard_warning:
        execution_mode = "REDUCED"
    elif (m5_aligned or m15_aligned) and candle_bonus >= 4.0:
        execution_mode = "FULL_ENTRY"
    elif candle_bonus > 0 or mtf_bonus > 0:
        execution_mode = "REDUCED"
    else:
        execution_mode = "NEUTRAL"

    aligned = m5_aligned or m15_aligned

    # ── Structured Log ───────────────────────────────────────────────
    log_line = (
        f"🕯 CANDLE_ENGINE"
        f" | TF=M5 Pattern={m5_pat} Str={m5_str:.0f} Bonus={bonus_m5:+.1f}"
        f" | TF=M15 Pattern={m15_pat} Str={m15_str:.0f} Bonus={bonus_m15:+.1f}"
        f" | Penalty={candle_penalty:+.0f} HardWarn={hard_warning}"
        f" | {mtf_reason} MTF_Bonus={mtf_bonus:+d}"
        f" | Delta={composite_delta:+.1f} Final={final_score:.1f}"
        f" | Mode={execution_mode} HardBlock={hard_block}"
        f" | Aligned={aligned} DupM5={m5_dup} DupM15={m15_dup}"
    )

    return {
        "candle_bonus":     round(candle_bonus, 2),
        "candle_penalty":   round(candle_penalty, 2),
        "hard_warning":     hard_warning,
        "hard_block":       hard_block,
        "mtf_bonus":        mtf_bonus,
        "mtf_reason":       mtf_reason,
        "composite_delta":  round(composite_delta, 2),
        "final_score":      final_score,
        "execution_mode":   execution_mode,
        "aligned":          aligned,
        "m5_aligned":       m5_aligned,
        "m15_aligned":      m15_aligned,
        "m5_opposite":      m5_opposite,
        "m15_opposite":     m15_opposite,
        "log_line":         log_line,
        # duplicate-guard flags for caller transparency
        "m5_duplicate":     m5_dup,
        "m15_duplicate":    m15_dup,
    }
