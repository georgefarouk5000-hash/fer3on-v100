from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"


def _read_main_source() -> str:
    return MAIN_PY.read_text(encoding="utf-8")


def test_production_ready_is_not_hardcoded_false():
    """The loss-pause-guard shortcut path used to hardcode
    production_ready=False unconditionally, making the watchdog report
    STARTUP_BLOCK on every single cycle the guard was active -- a
    completely normal, expected protective state, not a health problem.
    """
    source = _read_main_source()
    assert "production_ready=False" not in source


def test_production_ready_is_not_tied_to_trade_approval():
    """Neither run_watchdog_cycle() call site should tie production_ready
    to whether a trade was approved this specific heartbeat -- most
    heartbeats correctly reject a trade, so this conflated "normal
    rejection" with "system degraded", burying real health signals in
    near-constant false-alarm noise.
    """
    source = _read_main_source()
    assert "production_ready=runtime_decision.get('approved'" not in source
    assert "production_ready=snapshot['quality_gate'].get('approved'" not in source


def test_production_ready_is_derived_from_startup_health():
    """Both call sites should now feed production_ready from a genuine,
    one-time-computed startup health flag."""
    source = _read_main_source()
    assert "_system_startup_ready = startup_result.get('startup_status') == 'SYSTEM_READY'" in source

    # Split on each real call site and check the following chunk of source
    # (up to the next call site, or end of file) for the correct wiring --
    # avoids needing a full paren-balancing parser for a simple source check.
    # Only count occurrences immediately followed by a newline + indented
    # arguments (a real call), not the explanatory comment above that also
    # mentions "run_watchdog_cycle()" in prose.
    real_call_marker = "run_watchdog_cycle(\n"
    chunks = source.split(real_call_marker)
    call_site_chunks = chunks[1:]  # first chunk is everything before the first call
    assert len(call_site_chunks) >= 2, "expected at least 2 run_watchdog_cycle(...) call sites in main.py"
    for chunk in call_site_chunks:
        following_source = chunk[:1000]  # arguments are always well within this window
        assert "production_ready=_system_startup_ready" in following_source
