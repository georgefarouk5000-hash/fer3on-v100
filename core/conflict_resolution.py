"""
FER3ON V7 — INSTITUTIONAL CONFLICT RESOLUTION ENGINE
Adaptive arbitration + smart cooldown + controlled override
"""

import time


# =========================================
# GLOBAL AI STATE
# =========================================

LAST_CONFLICT_TIME = 0
CONFLICT_STREAK = 0
LAST_DECISION = "NONE"


# =========================================
# HELPERS
# =========================================

def _clamp(value, lower=0.0, upper=1.0):
    return max(lower, min(upper, float(value)))


def _safe_bool(value):
    return bool(value is True)


# =========================================
# VOLATILITY FILTER
# =========================================

def compute_volatility_penalty(volatility_state="NORMAL"):
    state = str(volatility_state or "NORMAL").upper()

    if state == "EXPLOSIVE":
        return 0.18

    if state == "HIGH":
        return 0.10

    if state == "LOW":
        return -0.03

    return 0.0


# =========================================
# SESSION FILTER
# =========================================

def compute_session_bonus(session_intelligence=50):
    score = float(session_intelligence or 50)

    if score >= 80:
        return 0.08

    if score >= 70:
        return 0.05

    if score <= 35:
        return -0.10

    return 0.0


# =========================================
# SMART CONFLICT MEMORY
# =========================================

def update_conflict_memory(decision):
    global LAST_CONFLICT_TIME
    global CONFLICT_STREAK
    global LAST_DECISION

    if decision in ("reject", "hold"):
        CONFLICT_STREAK += 1
        LAST_CONFLICT_TIME = time.time()
    else:
        CONFLICT_STREAK = 0

    LAST_DECISION = decision


def get_conflict_pressure():
    global CONFLICT_STREAK

    if CONFLICT_STREAK >= 5:
        return 0.15

    if CONFLICT_STREAK >= 3:
        return 0.08

    return 0.0


# =========================================
# INSTITUTIONAL ARBITRATION
# =========================================

def resolve_conflicting_signals(
    ai_score,
    structure_score,
    execution_score,
    risk_score,
    liquidity_score=0.50,
    session_intelligence=50,
    volatility_state="NORMAL",
    recovery_mode=False,
    mtf_alignment=False,
    smart_override=False,
):
    """
    Institutional-grade arbitration engine.

    Features:
    - adaptive weighted consensus
    - volatility suppression
    - session intelligence
    - smart recovery behavior
    - controlled override system
    - anti-overtrading pressure
    """

    ai_score = _clamp(ai_score)
    structure_score = _clamp(structure_score)
    execution_score = _clamp(execution_score)
    risk_score = _clamp(risk_score)
    liquidity_score = _clamp(liquidity_score)

    # =====================================
    # DYNAMIC WEIGHTS
    # =====================================

    weights = {
        "ai": 0.34,
        "structure": 0.22,
        "execution": 0.18,
        "risk": 0.16,
        "liquidity": 0.10,
    }

    if mtf_alignment:
        weights["structure"] += 0.05
        weights["ai"] -= 0.02

    if recovery_mode:
        weights["risk"] += 0.08
        weights["execution"] += 0.04
        weights["ai"] -= 0.06

    total = sum(weights.values())

    for k in weights:
        weights[k] = weights[k] / total

    # =====================================
    # BASE SCORE
    # =====================================

    weighted_score = (
        weights["ai"] * ai_score
        + weights["structure"] * structure_score
        + weights["execution"] * execution_score
        + weights["liquidity"] * liquidity_score
        + weights["risk"] * (1.0 - risk_score)
    )

    # =====================================
    # SESSION BONUS
    # =====================================

    session_bonus = compute_session_bonus(session_intelligence)

    # =====================================
    # VOLATILITY PENALTY
    # =====================================

    volatility_penalty = compute_volatility_penalty(volatility_state)

    # =====================================
    # CONFLICT PRESSURE
    # =====================================

    pressure_penalty = get_conflict_pressure()

    # =====================================
    # FINAL SCORE
    # =====================================

    final_score = (
        weighted_score
        + session_bonus
        - volatility_penalty
        - pressure_penalty
    )

    final_score = _clamp(final_score)

    # =====================================
    # DECISION ENGINE
    # =====================================

    if risk_score >= 0.88:
        decision = "reject"

    elif final_score <= 0.32:
        decision = "reject"

    elif risk_score >= 0.65 and final_score < 0.60:
        decision = "hold"

    elif volatility_state == "EXPLOSIVE" and final_score < 0.78:
        decision = "hold"

    elif final_score >= 0.82 and risk_score <= 0.42:
        decision = "approve"

    elif final_score >= 0.70:
        decision = "approve_reduced"

    else:
        decision = "hold"

    # =====================================
    # SMART OVERRIDE
    # =====================================

    override_applied = False

    if (
        smart_override
        and decision == "hold"
        and ai_score >= 0.92
        and execution_score >= 0.88
        and structure_score >= 0.75
        and risk_score <= 0.35
    ):
        decision = "approve_reduced"
        override_applied = True

    # =====================================
    # RECOVERY SAFETY
    # =====================================

    if recovery_mode and decision == "approve":
        decision = "approve_reduced"

    # =====================================
    # MEMORY UPDATE
    # =====================================

    update_conflict_memory(decision)

    # =====================================
    # DEBUG OUTPUT
    # =====================================

    print(
        f"🧠 CONFLICT_ENGINE"
        f" | final={round(final_score * 100, 2)}"
        f" | decision={decision.upper()}"
        f" | risk={round(risk_score * 100, 1)}%"
        f" | pressure={round(pressure_penalty * 100, 1)}%"
        f" | override={override_applied}"
    )

    # =====================================
    # RETURN
    # =====================================

    return {
        "final_score": round(final_score, 4),
        "decision": decision,
        "override_applied": override_applied,
        "session_bonus": round(session_bonus, 4),
        "volatility_penalty": round(volatility_penalty, 4),
        "pressure_penalty": round(pressure_penalty, 4),
        "weights": {
            "ai": round(weights["ai"], 3),
            "structure": round(weights["structure"], 3),
            "execution": round(weights["execution"], 3),
            "risk": round(weights["risk"], 3),
            "liquidity": round(weights["liquidity"], 3),
        },
        "state": {
            "conflict_streak": CONFLICT_STREAK,
            "last_decision": LAST_DECISION,
            "recovery_mode": _safe_bool(recovery_mode),
            "mtf_alignment": _safe_bool(mtf_alignment),
        },
    }