# =========================================
# FER3ON V7 — SCALE-IN EXECUTION LAYER
# Add to winners only — never average losers
# =========================================

from core.settings import V7_SCALE_IN_ENABLED, MIN_LOT, MAX_LOT


def confidence_to_scale_pct(confidence_score):
    """
    Position sizing scale by confidence:
      55–64 → 25%
      65–74 → 50%
      75–84 → 75%
      85+   → 100%
    """
    conf = float(confidence_score or 0)
    if conf >= 85:
        return 1.00
    if conf >= 75:
        return 0.75
    if conf >= 65:
        return 0.50
    if conf >= 55:
        return 0.25
    return 0.0


def is_position_in_profit(position, current_price):
    """True if open position is in unrealized profit."""
    if position is None or current_price <= 0:
        return False
    entry = float(getattr(position, "price_open", 0) or 0)
    if entry <= 0:
        return False
    pos_type = int(getattr(position, "type", -1))
    # MT5: 0=BUY, 1=SELL
    if pos_type == 0:
        return current_price > entry
    if pos_type == 1:
        return current_price < entry
    return False


def evaluate_scale_in(
    position,
    current_price,
    confidence_score,
    risk_blocked=False,
    already_scaled=False,
    base_lot=0.01,
):
    """
    Evaluate whether to scale into an existing winning position.
    Returns approval dict — never averages losers.
    """
    if not V7_SCALE_IN_ENABLED:
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": 0.0,
            "reason": "V7_SCALE_IN_DISABLED",
            "enabled": False,
        }

    if risk_blocked:
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": 0.0,
            "reason": "RISK_BLOCKED",
            "enabled": True,
        }

    if already_scaled:
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": 0.0,
            "reason": "ALREADY_SCALED",
            "enabled": True,
        }

    if not is_position_in_profit(position, current_price):
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": 0.0,
            "reason": "NOT_IN_PROFIT",
            "enabled": True,
        }

    scale_pct = confidence_to_scale_pct(confidence_score)
    if scale_pct <= 0:
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": 0.0,
            "reason": "CONFIDENCE_TOO_LOW",
            "enabled": True,
        }

    current_vol = float(getattr(position, "volume", 0) or base_lot)
    add_volume = round(current_vol * scale_pct, 2)
    add_volume = max(MIN_LOT, min(add_volume, MAX_LOT - current_vol))

    if add_volume < MIN_LOT:
        return {
            "approved": False,
            "add_volume": 0.0,
            "scale_pct": scale_pct,
            "reason": "ADD_VOLUME_TOO_SMALL",
            "enabled": True,
        }

    print(
        f"[FER3ON AI V2] SCALE_IN: approved"
        f" | conf={confidence_score}"
        f" | scale={scale_pct:.0%}"
        f" | add={add_volume}"
    )

    return {
        "approved": True,
        "add_volume": add_volume,
        "scale_pct": scale_pct,
        "reason": f"SCALE_IN_{int(scale_pct * 100)}PCT",
        "enabled": True,
    }
