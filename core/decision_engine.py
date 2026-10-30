# =========================================
# FER3ON SUPREME DECISION ENGINE V6
# Adaptive AI Authority Decision Core
# =========================================

def make_decision(

    ai_score,
    memory_score,
    session_score,
    brain_confidence,
    dna_score,
    crisis_multiplier,
    signal,

    # NEW
    ai_authority_score=50,
    aggression_modifier=1.0,
    velocity_score=50,
    execution_quality=50,
    liquidity_alignment=50,
    recent_losses=0,
    false_rejection_rate=0,
    session_phase="NORMAL",
    regime="RANGING",
):

    # =====================================
    # ADAPTIVE WEIGHTS
    # =====================================

    ai_weight = 0.30
    memory_weight = 0.18
    brain_weight = 0.20
    session_weight = 0.12
    dna_weight = 0.08
    crisis_weight = 0.12

    # =====================================
    # AI AUTHORITY BOOST
    # =====================================

    if ai_authority_score >= 85:
        ai_weight += 0.10
        memory_weight -= 0.03
        session_weight -= 0.02

    # =====================================
    # EXECUTION BOOSTS
    # =====================================

    execution_bonus = (
        velocity_score * 0.10 +
        execution_quality * 0.10 +
        liquidity_alignment * 0.10
    ) / 3

    # =====================================
    # FALSE REJECTION RECOVERY
    # =====================================

    recovery_bonus = 0

    if false_rejection_rate >= 30:
        recovery_bonus += 4

    if false_rejection_rate >= 50:
        recovery_bonus += 6

    # =====================================
    # SESSION BOOST
    # =====================================

    session_bonus = 0

    if session_phase in [
        "LONDON_SWEEP",
        "OVERLAP",
        "NY_OPEN"
    ]:
        session_bonus += 5

    # =====================================
    # REGIME BOOST
    # =====================================

    regime_bonus = 0

    if regime in [
        "EXPLOSIVE",
        "LIQUIDITY_SWEEP",
        "STOP_HUNT"
    ]:
        regime_bonus += 6

    # =====================================
    # LOSS PROTECTION
    # =====================================

    protection_penalty = 0

    if recent_losses >= 2:
        protection_penalty += 5

    if recent_losses >= 3:
        protection_penalty += 10

    # =====================================
    # FINAL SCORE
    # =====================================

    final_score = (

        ai_score * ai_weight +

        memory_score * memory_weight +

        brain_confidence * brain_weight +

        session_score * session_weight +

        dna_score * dna_weight +

        (crisis_multiplier * 100) * crisis_weight +

        execution_bonus +

        recovery_bonus +

        session_bonus +

        regime_bonus -

        protection_penalty

    )

    # =====================================
    # AGGRESSION MODIFIER
    # =====================================

    final_score *= aggression_modifier

    final_score = round(
        max(0, min(100, final_score)),
        2
    )

    # =====================================
    # AI OVERRIDE LOGIC
    # =====================================

    ai_override = False

    if (
        ai_authority_score >= 90
        and ai_score >= 80
        and brain_confidence >= 75
    ):
        ai_override = True

    # =====================================
    # DECISION LAYERS
    # =====================================

    if final_score < 45 and not ai_override:

        return {

            "decision": "NONE",

            "score": final_score,

            "risk_multiplier": 0,

            "ai_override": False,

            "mode": "REJECT"

        }

    # =====================================
    # DEFENSIVE ENTRY
    # =====================================

    if final_score < 60:

        return {

            "decision": signal,

            "score": final_score,

            "risk_multiplier": 0.35,

            "ai_override": ai_override,

            "mode": "DEFENSIVE"

        }

    # =====================================
    # BALANCED ENTRY
    # =====================================

    if final_score < 75:

        return {

            "decision": signal,

            "score": final_score,

            "risk_multiplier": 0.75,

            "ai_override": ai_override,

            "mode": "BALANCED"

        }

    # =====================================
    # AGGRESSIVE ENTRY
    # =====================================

    if final_score < 88:

        return {

            "decision": signal,

            "score": final_score,

            "risk_multiplier": 1.10,

            "ai_override": ai_override,

            "mode": "AGGRESSIVE"

        }

    # =====================================
    # PREDATOR MODE
    # =====================================

    return {

        "decision": signal,

        "score": final_score,

        "risk_multiplier": 1.35,

        "ai_override": ai_override,

        "mode": "PREDATOR"

    }