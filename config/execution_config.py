"""Execution and routing configuration."""

EXECUTION_CONFIG = {
    "max_concurrent_positions": 3,
    "cooldown_seconds": 180,
    "probe_entry_enabled": True,
    "scale_in_enabled": True,
    "scale_in_levels": 2,
    "max_entry_retries": 2,
    "max_slippage_points": 4,
    "execution_timeout_seconds": 5,
    "allow_duplicate_entries": False,
}


def get_execution_config():
    return dict(EXECUTION_CONFIG)
