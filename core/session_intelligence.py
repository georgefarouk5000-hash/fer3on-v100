# =========================================
# FER3ON V6 Recovery++ — SESSION INTELLIGENCE ENGINE
# Adaptive AI Session Brain + Controlled Aggression
# Smart cooldown + dynamic execution modifiers
# =========================================

from typing import Any, Dict

from core.ai_memory import load_memory_records
from core.data_integrity import get_session_from_hour
from core.settings import (
    V7_PLUS_ENABLED,
    V7_SESSION_INTELLIGENCE_ENABLED,
)

MEMORY_FILE = "data/memory/ai_memory.csv"

# =========================================
# SESSION PHASES
# =========================================

SESSION_PHASES = {
    "ASIA": {"start": 0, "end": 8},
    "LONDON_OPEN": {"start": 8, "end": 9},
    "LONDON_SWEEP": {"start": 9, "end": 10},
    "LONDON_EXPANSION": {"start": 10, "end": 13},
    "NY_OPEN": {"start": 13, "end": 14},
    "OVERLAP": {"start": 13, "end": 16},
    "NY_EXPANSION": {"start": 14, "end": 18},
    "OFF_HOURS": {"start": 18, "end": 24},
}

# =========================================
# SMART PHASE MODIFIERS
# =========================================

PHASE_MODIFIERS = {
    "ASIA": {
        "confidence": -2.0,
        "risk": 0.92,
        "velocity": 0.95,
        "threshold": +1.0,
        "score_base": 52.0,
        "aggression": 0.88,
        "cooldown": 8,
    },

    "LONDON_OPEN": {
        "confidence": +4.0,
        "risk": 1.08,
        "velocity": 1.15,
        "threshold": -4.0,
        "score_base": 72.0,
        "aggression": 1.12,
        "cooldown": 3,
    },

    "LONDON_SWEEP": {
        "confidence": +6.0,
        "risk": 1.15,
        "velocity": 1.22,
        "threshold": -7.0,
        "score_base": 82.0,
        "aggression": 1.22,
        "cooldown": 2,
    },

    "LONDON_EXPANSION": {
        "confidence": +5.0,
        "risk": 1.12,
        "velocity": 1.18,
        "threshold": -5.0,
        "score_base": 78.0,
        "aggression": 1.18,
        "cooldown": 2,
    },

    "NY_OPEN": {
        "confidence": +7.0,
        "risk": 1.18,
        "velocity": 1.25,
        "threshold": -8.0,
        "score_base": 88.0,
        "aggression": 1.30,
        "cooldown": 2,
    },

    "OVERLAP": {
        "confidence": +9.0,
        "risk": 1.22,
        "velocity": 1.32,
        "threshold": -10.0,
        "score_base": 94.0,
        "aggression": 1.38,
        "cooldown": 1,
    },

    "NY_EXPANSION": {
        "confidence": +5.0,
        "risk": 1.10,
        "velocity": 1.15,
        "threshold": -5.0,
        "score_base": 74.0,
        "aggression": 1.16,
        "cooldown": 3,
    },

    "OFF_HOURS": {
        "confidence": -10.0,
        "risk": 0.70,
        "velocity": 0.75,
        "threshold": +10.0,
        "score_base": 25.0,
        "aggression": 0.60,
        "cooldown": 15,
    },
}

# =========================================
# BACKWARD COMPATIBILITY
# =========================================

def get_session(hour: int) -> str:
    return get_session_from_hour(hour)


def get_session_confidence(current_hour: int) -> float:
    rows = load_memory_records()

    if not rows:
        return 50.0

    target_session = get_session(current_hour)

    wins = 0
    total = 0

    for row in rows:
        session = row.get("session") or get_session(row.get("hour", 0))

        if session != target_session:
            continue

        total += 1

        if str(row.get("result", "")).upper() == "WIN":
            wins += 1

    if total < 5:
        return 50.0

    return round((wins / total) * 100, 2)

# =========================================
# DETECT SESSION PHASE
# =========================================

def detect_session_phase(hour: int, minute: int = 0) -> str:
    try:
        h = int(hour)
    except Exception:
        return "OFF_HOURS"

    if 13 <= h < 16:
        return "OVERLAP"

    if 13 <= h < 14:
        return "NY_OPEN"

    if 14 <= h < 18:
        return "NY_EXPANSION"

    if 8 <= h < 9:
        return "LONDON_OPEN"

    if 9 <= h < 10:
        return "LONDON_SWEEP"

    if 10 <= h < 13:
        return "LONDON_EXPANSION"

    if 0 <= h < 8:
        return "ASIA"

    return "OFF_HOURS"

# =========================================
# GET PHASE MODIFIERS
# =========================================

def get_phase_modifiers(phase: str) -> Dict[str, float]:
    return dict(
        PHASE_MODIFIERS.get(
            str(phase or "OFF_HOURS").upper(),
            PHASE_MODIFIERS["OFF_HOURS"]
        )
    )

# =========================================
# SESSION SCORE
# =========================================

def compute_session_intelligence_score(
    phase: str,
    historical_confidence: float,
    signal: str = "NONE",
) -> float:

    mods = get_phase_modifiers(phase)

    base = float(mods.get("score_base", 50.0))
    hist = float(historical_confidence or 50.0)

    score = (base * 0.65) + (hist * 0.35)

    signal = str(signal or "NONE").upper()

    if signal in ("BUY", "SELL"):
        score += 2.0

    return round(min(100.0, max(0.0, score)), 2)

# =========================================
# MAIN SESSION AI
# =========================================

def analyze_session_intelligence(
    hour: int,
    signal: str = "NONE",
    minute: int = 0,
    recent_losses: int = 0,
    current_drawdown: float = 0.0,
) -> Dict[str, Any]:

    if not V7_PLUS_ENABLED or not V7_SESSION_INTELLIGENCE_ENABLED:
        session = get_session(hour)
        hist = get_session_confidence(hour)

        return {
            "enabled": False,
            "session": session,
            "phase": session,
            "session_intelligence_score": hist,
            "confidence_modifier": 0.0,
            "risk_modifier": 1.0,
            "velocity_modifier": 1.0,
            "threshold_modifier": 0.0,
            "aggression_modifier": 1.0,
            "cooldown_minutes": 0,
            "historical_confidence": hist,
            "reason": "DISABLED",
        }

    session = get_session(hour)

    phase = detect_session_phase(hour, minute)

    hist = get_session_confidence(hour)

    mods = get_phase_modifiers(phase)

    score = compute_session_intelligence_score(
        phase,
        hist,
        signal,
    )

    confidence_modifier = float(mods["confidence"])
    risk_modifier = float(mods["risk"])
    velocity_modifier = float(mods["velocity"])
    threshold_modifier = float(mods["threshold"])
    aggression_modifier = float(mods["aggression"])
    cooldown_minutes = int(mods["cooldown"])

    # =========================================
    # SMART LOSS REACTION
    # =========================================

    if recent_losses >= 2:
        confidence_modifier -= 4.0
        aggression_modifier *= 0.85
        cooldown_minutes += 5

    if recent_losses >= 3:
        risk_modifier *= 0.75
        threshold_modifier += 4.0
        aggression_modifier *= 0.75
        cooldown_minutes += 10

    # =========================================
    # DRAWDOWN PROTECTION
    # =========================================

    if current_drawdown >= 3.0:
        risk_modifier *= 0.80
        aggression_modifier *= 0.80

    if current_drawdown >= 5.0:
        risk_modifier *= 0.60
        aggression_modifier *= 0.65
        threshold_modifier += 5.0
        cooldown_minutes += 15

    # =========================================
    # SMART AGGRESSION BOOST
    # =========================================

    if phase in ("LONDON_SWEEP", "OVERLAP", "NY_OPEN"):
        aggression_mode = "HIGH_PRECISION_AGGRESSION"
    elif phase in ("ASIA", "OFF_HOURS"):
        aggression_mode = "DEFENSIVE_EXECUTION"
    else:
        aggression_mode = "BALANCED_EXECUTION"

    result = {
        "enabled": True,
        "session": session,
        "phase": phase,
        "session_intelligence_score": score,

        "confidence_modifier": round(confidence_modifier, 2),
        "risk_modifier": round(risk_modifier, 2),
        "velocity_modifier": round(velocity_modifier, 2),
        "threshold_modifier": round(threshold_modifier, 2),

        "aggression_modifier": round(aggression_modifier, 2),
        "cooldown_minutes": cooldown_minutes,

        "historical_confidence": hist,
        "aggression_mode": aggression_mode,

        "reason": "ACTIVE",
    }

    print(
        f"[RECOVERY++] SESSION_INTEL"
        f" | phase={phase}"
        f" | score={score}"
        f" | conf_mod={confidence_modifier:+.1f}"
        f" | risk_mod={risk_modifier:.2f}"
        f" | aggression={aggression_modifier:.2f}"
        f" | cooldown={cooldown_minutes}m"
        f" | mode={aggression_mode}"
    )

    return result