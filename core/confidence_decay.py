# =========================================
# FER3ON V7 — CONFIDENCE DECAY SYSTEM
# Prevents stale setups from executing
# =========================================

import time

from core.settings import V7_CONFIDENCE_DECAY_ENABLED


def compute_decay_steps(elapsed_seconds, atr, session="UNKNOWN"):
    """
    Number of decay steps based on elapsed time, ATR, session.
    Faster decay in off-hours / low ATR.
    """
    if elapsed_seconds <= 0:
        return 0

    base_interval = 120.0
    session = str(session or "UNKNOWN").upper()
    if session in ("OFF_HOURS", "ASIA"):
        base_interval = 90.0
    elif session in ("LONDON", "NEWYORK", "OVERLAP"):
        base_interval = 150.0

    atr = float(atr or 1.0)
    if atr < 2.0:
        base_interval *= 0.85
    elif atr > 5.0:
        base_interval *= 1.15

    return int(elapsed_seconds // base_interval)


def apply_confidence_decay(initial_confidence, elapsed_seconds, atr, session="UNKNOWN", points_per_step=4):
    """
    Apply step decay to confidence.
    Example: 72 → 68 → 64 → 60 → 55
    """
    initial = float(initial_confidence or 0)
    if not V7_CONFIDENCE_DECAY_ENABLED:
        return {
            "decayed_confidence": round(initial, 2),
            "decay_applied": 0.0,
            "steps": 0,
            "enabled": False,
        }

    steps = compute_decay_steps(elapsed_seconds, atr, session)
    decay_applied = steps * float(points_per_step)
    decayed = max(0.0, initial - decay_applied)

    result = {
        "decayed_confidence": round(decayed, 2),
        "decay_applied": round(decay_applied, 2),
        "steps": steps,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "enabled": True,
    }

    if steps > 0:
        print(
            f"[FER3ON AI V2] CONFIDENCE_DECAY: {initial:.1f} -> {decayed:.1f}"
            f" | steps={steps}"
            f" | elapsed={elapsed_seconds:.0f}s"
        )

    return result


class SetupDecayTracker:
    """Track setup birth time for decay before execution."""

    def __init__(self):
        self._setups = {}

    def _key(self, strategy, signal, symbol):
        return f"{symbol}:{strategy}:{signal}"

    def touch(self, strategy, signal, symbol):
        key = self._key(strategy, signal, symbol)
        if key not in self._setups:
            self._setups[key] = time.time()
        return self._setups[key]

    def clear(self, strategy, signal, symbol):
        self._setups.pop(self._key(strategy, signal, symbol), None)

    def get_decayed_confidence(self, strategy, signal, symbol, initial_confidence, atr, session):
        key = self._key(strategy, signal, symbol)
        started = self._setups.get(key)
        if started is None:
            started = time.time()
            self._setups[key] = started
        elapsed = time.time() - started
        return apply_confidence_decay(initial_confidence, elapsed, atr, session)


setup_decay_tracker = SetupDecayTracker()
