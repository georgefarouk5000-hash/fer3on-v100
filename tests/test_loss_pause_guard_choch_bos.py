import time

import core.loss_pause_guard as lpg


def _snapshot(structure_analysis=None, structure=None, choch_state=None, bos_state=None, signal='BUY'):
    snap = {'signal': signal}
    if structure is not None:
        snap['structure'] = structure
    if structure_analysis is not None:
        snap['structure_analysis'] = structure_analysis
    if choch_state is not None:
        snap['choch_state'] = choch_state
    if bos_state is not None:
        snap['bos_state'] = bos_state
    return snap


# --------------------- _fetch_choch_bos: data source ---------------------

def test_reads_choch_from_structure_analysis():
    """The real bug: main.py's actual snapshot shape has no
    structure['choch_h1'/'choch_h4'] and no top-level snapshot['choch_state']
    -- the genuinely-computed value lives at
    snapshot['structure_analysis']['choch']."""
    snap = _snapshot(structure_analysis={'choch': 'CHOCH_BULLISH', 'bos': 'NONE'})
    result = lpg._fetch_choch_bos(snap)
    assert result['choch'] == 'CHOCH_BULLISH'


def test_reads_bos_from_structure_analysis():
    snap = _snapshot(structure_analysis={'choch': 'NONE', 'bos': 'BOS_UP'})
    result = lpg._fetch_choch_bos(snap)
    assert result['bos'] == 'BOS_UP'


def test_falls_back_to_legacy_structure_keys_when_present():
    # Backward compatibility: some other caller might still pass the old
    # (never actually populated by main.py, but theoretically valid) shape.
    snap = _snapshot(structure={'choch_h1': 'CHOCH_BEARISH'}, structure_analysis={})
    result = lpg._fetch_choch_bos(snap)
    assert result['choch'] == 'CHOCH_BEARISH'


def test_realistic_main_py_snapshot_shape_without_fresh_signal_returns_none():
    # Matches the exact shape main.py builds when structure genuinely has
    # no fresh CHOCH/BOS this cycle -- must correctly report NONE, not
    # silently swallow a real signal (the mirror-image failure mode).
    snap = _snapshot(
        structure={'structure': 'BEARISH_STRUCTURE', 'bias': 'SELL', 'mtf_aligned': False},
        structure_analysis={'choch': 'NONE', 'bos': 'NONE', 'structure_bias': 'SELL'},
    )
    result = lpg._fetch_choch_bos(snap)
    assert result['choch'] == 'NONE'
    assert result['bos'] == 'NONE'


# --------------------- evaluate_loss_pause: full lifecycle ---------------------

def _reset_guard(tmp_state_file):
    lpg._save_state({
        'consecutive_losses': 0,
        'pause_active': False,
        'pause_start_timestamp': 0.0,
        'last_signal_signature': '',
    })


def test_guard_stays_blocked_without_a_fresh_signal(tmp_path, monkeypatch):
    state_file = str(tmp_path / "loss_pause_guard.json")
    monkeypatch.setattr(lpg, "_STATE_PATH", state_file)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_TRIGGER", 2)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_REQUIRE_REGIME", ("TRENDING",))

    lpg.register_trade_result('LOSS', ticket=1, profit=-5.0)
    lpg.register_trade_result('LOSS', ticket=2, profit=-5.0)

    snap = _snapshot(structure_analysis={'choch': 'NONE', 'bos': 'NONE'})
    result = lpg.evaluate_loss_pause(snap, market_regime='TRENDING')

    assert result['trading_allowed'] is False
    assert 'AWAITING_FRESH_CHOCH_OR_BOS' in result['reason']


def test_guard_lifts_on_fresh_choch_from_structure_analysis(tmp_path, monkeypatch):
    """This is the core regression test: before the fix, no snapshot shape
    main.py actually produces could ever set has_bullish/has_bearish to
    True, so this exact scenario would have stayed blocked forever. After
    the fix, a genuine CHOCH in structure_analysis correctly lifts the
    pause.
    """
    state_file = str(tmp_path / "loss_pause_guard.json")
    monkeypatch.setattr(lpg, "_STATE_PATH", state_file)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_TRIGGER", 2)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_REQUIRE_REGIME", ("TRENDING",))
    monkeypatch.setattr(lpg, "LOSS_PAUSE_COOLDOWN_SEC", 0)

    lpg.register_trade_result('LOSS', ticket=1, profit=-5.0)
    lpg.register_trade_result('LOSS', ticket=2, profit=-5.0)

    # First check with no fresh signal -- still blocked (sets a baseline
    # signature).
    blocked = lpg.evaluate_loss_pause(
        _snapshot(structure_analysis={'choch': 'NONE', 'bos': 'NONE'}, signal='SELL'),
        market_regime='TRENDING',
    )
    assert blocked['trading_allowed'] is False

    # A fresh CHOCH appears -- must lift the pause.
    lifted = lpg.evaluate_loss_pause(
        _snapshot(structure_analysis={'choch': 'CHOCH_BULLISH', 'bos': 'NONE'}, signal='BUY'),
        market_regime='TRENDING',
    )
    assert lifted['trading_allowed'] is True
    assert lifted['reason'] == 'FRESH_CHOCH_OR_BOS'
    assert lifted['consecutive_losses'] == 0


def test_guard_lifts_on_fresh_bos_from_structure_analysis(tmp_path, monkeypatch):
    state_file = str(tmp_path / "loss_pause_guard.json")
    monkeypatch.setattr(lpg, "_STATE_PATH", state_file)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_TRIGGER", 2)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_REQUIRE_REGIME", ("TRENDING",))
    monkeypatch.setattr(lpg, "LOSS_PAUSE_COOLDOWN_SEC", 0)

    lpg.register_trade_result('LOSS', ticket=1, profit=-5.0)
    lpg.register_trade_result('LOSS', ticket=2, profit=-5.0)

    lpg.evaluate_loss_pause(
        _snapshot(structure_analysis={'choch': 'NONE', 'bos': 'NONE'}, signal='SELL'),
        market_regime='TRENDING',
    )
    lifted = lpg.evaluate_loss_pause(
        _snapshot(structure_analysis={'choch': 'NONE', 'bos': 'BOS_DOWN'}, signal='SELL'),
        market_regime='TRENDING',
    )
    assert lifted['trading_allowed'] is True


def test_existing_structure_is_not_fresh_when_pause_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(lpg, "_STATE_PATH", str(tmp_path / "loss_pause_guard.json"))
    monkeypatch.setattr(lpg, "LOSS_PAUSE_TRIGGER", 2)
    monkeypatch.setattr(lpg, "LOSS_PAUSE_REQUIRE_REGIME", ("TRENDING",))
    monkeypatch.setattr(lpg, "LOSS_PAUSE_COOLDOWN_SEC", 0)
    lpg.register_trade_result("LOSS", ticket=1, profit=-5.0)
    lpg.register_trade_result("LOSS", ticket=2, profit=-5.0)

    existing_bos = _snapshot(structure_analysis={"choch": "NONE", "bos": "BOS_UP"})
    assert not lpg.evaluate_loss_pause(existing_bos, "TRENDING")["trading_allowed"]
    assert not lpg.evaluate_loss_pause(existing_bos, "TRENDING")["trading_allowed"]

    fresh_choch = _snapshot(
        structure_analysis={"choch": "CHOCH_BULLISH", "bos": "BOS_UP"}
    )
    assert lpg.evaluate_loss_pause(fresh_choch, "TRENDING")["trading_allowed"]
