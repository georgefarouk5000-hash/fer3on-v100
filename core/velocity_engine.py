# =========================================
# FER3ON V7 — VELOCITY ENGINE
# Market acceleration modifier (not a signal)
# =========================================

from core.settings import V7_VELOCITY_ENABLED, V7_VELOCITY_MAX_BONUS


def compute_velocity(close_now, close_5_bars_ago, atr):
    """
    velocity = abs(close_now - close_5_bars_ago) / ATR
    Returns 0 if ATR invalid.
    """
    if atr is None or float(atr) <= 0:
        return 0.0
    return abs(float(close_now) - float(close_5_bars_ago)) / float(atr)


def classify_velocity(velocity):
    """
    <0.8       WEAK
    0.8–1.2    NORMAL
    1.2–1.8    STRONG
    >1.8       EXPLOSIVE
    """
    v = float(velocity or 0)
    if v < 0.8:
        return "WEAK"
    if v < 1.2:
        return "NORMAL"
    if v < 1.8:
        return "STRONG"
    return "EXPLOSIVE"


def velocity_confidence_bonus(velocity):
    """
    Confidence bonus 0 to +10 max.
    Used only as modifier, never standalone signal.
    """
    if not V7_VELOCITY_ENABLED:
        return 0.0

    v = float(velocity or 0)
    if v < 0.8:
        bonus = 0.0
    elif v < 1.2:
        bonus = 2.0
    elif v < 1.8:
        bonus = 6.0
    else:
        bonus = float(V7_VELOCITY_MAX_BONUS)

    return min(float(V7_VELOCITY_MAX_BONUS), bonus)


def analyze_velocity_from_closes(closes, atr):
    """
    Full velocity analysis from close series (needs >= 6 bars).
  Returns dict with velocity, classification, bonus, score.
    """
    if not closes or len(closes) < 6:
        return {
            "velocity": 0.0,
            "classification": "WEAK",
            "confidence_bonus": 0.0,
            "velocity_score": 0.0,
            "enabled": V7_VELOCITY_ENABLED,
        }

    vel = compute_velocity(closes[-1], closes[-6], atr)
    classification = classify_velocity(vel)
    bonus = velocity_confidence_bonus(vel)
    velocity_score = round(min(100.0, vel / 2.0 * 100), 2)

    result = {
        "velocity": round(vel, 4),
        "classification": classification,
        "confidence_bonus": round(bonus, 2),
        "velocity_score": velocity_score,
        "enabled": V7_VELOCITY_ENABLED,
    }

    if V7_VELOCITY_ENABLED:
        print(
            f"[FER3ON AI V2] VELOCITY: {vel:.3f} ({classification})"
            f" | bonus=+{bonus:.1f}"
            f" | score={velocity_score}"
        )

    return result
