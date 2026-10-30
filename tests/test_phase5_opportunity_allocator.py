"""PHASE 5 — Opportunity Allocator tests."""
import core.opportunity_allocator as oa
import core.settings as settings


def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(settings, "PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED",
                        False, raising=False)
    monkeypatch.setattr(settings, "DAILY_PROFIT_LOCK_DOLLARS", 30.0,
                        raising=False)
    monkeypatch.setattr(settings, "ALLOCATOR_MIN_SAMPLES", 30, raising=False)
    monkeypatch.setattr(settings, "ALLOCATOR_BASE_RISK_R", 0.25, raising=False)


def test_score_multiplicative_zero_kills():
    assert oa.compute_opportunity_score(0.9, 0.9, 0.0, 0.9, 0.9) == 0.0
    s = oa.compute_opportunity_score(1, 1, 1, 1, 1)
    assert s == 1.0
    s = oa.compute_opportunity_score(0.5, 0.5, 0.5, 0.5, 0.5)
    assert 0 < s < 0.1  # multiplicative decay


def test_daily_states(monkeypatch):
    _cfg(monkeypatch)
    assert oa.classify_daily_state(0, consecutive_losses=2) == "SURVIVAL"
    assert oa.classify_daily_state(35.0) == "PROTECTION"   # profit lock
    assert oa.profit_lock_active(30.0) is True
    assert oa.classify_daily_state(10.0, regime_clear=True) == "OPPORTUNITY"
    assert oa.classify_daily_state(10.0, regime_clear=False) == "NORMAL"
    assert oa.classify_daily_state(0, consecutive_losses=0) == "NORMAL"


def test_risk_needs_proven_results(monkeypatch):
    _cfg(monkeypatch)
    # high score but NO proven bucket -> base risk only
    assert oa.recommend_risk_r(0.9, None) == 0.25
    assert oa.recommend_risk_r(0.9, {"n": 5, "win_rate": 0.9, "pnl": 50}) == 0.25
    # proven bucket unlocks tiers
    proven = {"n": 40, "win_rate": 0.6, "pnl": 120.0}
    assert oa.recommend_risk_r(0.45, proven) == 0.75
    assert oa.recommend_risk_r(0.30, proven) == 0.50
    assert oa.recommend_risk_r(0.10, proven) == 0.25
    assert oa.recommend_risk_r(0.0, proven) == 0.0


def test_evaluate_skip_paths(monkeypatch, tmp_path):
    _cfg(monkeypatch)
    monkeypatch.setattr(settings, "PHASE5_ALLOCATOR_LOG_PATH",
                        str(tmp_path / "eval.jsonl"), raising=False)
    good = {"signal_id": "s1", "edge": 0.8, "probability": 0.7,
            "market_space": 0.8, "execution_quality": 0.8,
            "regime_fit": 0.9, "strategy": "SMC"}
    # survival blocks everything
    r = oa.evaluate_opportunity(good, daily_pnl=0, consecutive_losses=3)
    assert r["action"] == "SKIP" and r["daily_state"] == "SURVIVAL"
    # profit lock blocks non-exceptional
    r = oa.evaluate_opportunity(good, daily_pnl=40)
    assert r["daily_state"] == "PROTECTION"
    assert r["action"] == "SKIP" and r["reason"] == "PROFIT_LOCK_ACTIVE"
    # zero edge -> skip
    r = oa.evaluate_opportunity({"edge": 0}, daily_pnl=0)
    assert r["action"] == "SKIP"
    # normal day + decent score -> take at base risk
    r = oa.evaluate_opportunity(good, daily_pnl=0)
    assert r["action"] == "TAKE" and r["risk_r"] == 0.25
    assert r["live"] is False  # advisory only


def test_disabled_and_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED",
                        False, raising=False)
    r = oa.evaluate_opportunity(None)
    assert r["enabled"] is False and r["action"] == "SKIP"
    monkeypatch.setattr(settings, "PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED",
                        True, raising=False)
    r = oa.evaluate_opportunity({"edge": object()})
    assert r["action"] in ("SKIP", "TAKE")
