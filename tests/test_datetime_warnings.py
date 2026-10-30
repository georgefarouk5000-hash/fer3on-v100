import warnings

from core.professional_logging import log_system_event
from core.watchdog import collect_watchdog_status


def test_datetime_helpers_do_not_emit_deprecation_warnings():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        log_system_event("hello", level="INFO")
        collect_watchdog_status()

    assert not any("datetime.datetime.utcnow" in str(w.message) for w in captured)
