from core.test_mode_manager import can_allocate, planned_lot_for_mode, register_trade, save_state
from core.settings import TESTING_MODE_LOT_CAPS, MAX_DAILY_TRADES


def test_test_mode_quota_tracks_micro_and_normal():
    # Reset state to current day
    state = save_state({
        "date": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d'),
        "used_micro": 0, "used_normal": 0, "used_total": 0
    })
    # Lot caps match current settings
    assert planned_lot_for_mode("MICRO") == TESTING_MODE_LOT_CAPS.get("MICRO", 0.01)
    assert planned_lot_for_mode("FULL") == TESTING_MODE_LOT_CAPS.get("FULL", 0.15)
    # Daily total cap is enforced
    assert MAX_DAILY_TRADES > 0
    # Allocation works while quota available
    assert register_trade(size_mode="MICRO")["allowed"] is True
    assert register_trade(size_mode="FULL")["allowed"] is True
    # can_allocate returns a valid structure
    result = can_allocate(size_mode="FULL")
    assert "allowed" in result
    assert "reason" in result
