import core.risk_manager as risk_manager


def _daily_loss_status(*, daily_loss, daily_used, daily_limit=10.0):
    return {
        "daily_used": daily_used,
        "weekly_used": daily_used * 3,
        "daily_limit": daily_limit,
        "weekly_limit": daily_limit * 4,
        "daily_loss_usd": daily_loss,
        "daily_loss_limit_usd": 100.0,
        "daily_remaining": max(0.0, daily_limit - daily_used),
        "weekly_remaining": max(0.0, daily_limit * 4 - daily_used * 3),
        "consecutive_losses": 0,
        "source": "test",
    }


def test_daily_limit_returns_zero_lot_instead_of_min_lot(monkeypatch):
    monkeypatch.setattr(risk_manager, "cooldown_active", lambda: False)
    monkeypatch.setattr(
        risk_manager,
        "get_loss_limits_status",
        lambda **_kwargs: _daily_loss_status(
            daily_loss=100.0,
            daily_used=10.0,
        ),
    )

    lot, _raw_lot, adjustments = risk_manager.calculate_smart_lot(
        balance=1000.0,
        risk_percent=0.5,
        sl_dist=10.0,
    )

    assert lot == 0.0
    assert "RISK_LIMITS_HIT" in adjustments


def test_trade_size_is_capped_by_remaining_daily_loss_budget(monkeypatch):
    monkeypatch.setattr(risk_manager, "cooldown_active", lambda: False)
    monkeypatch.setattr(risk_manager, "TESTING_MODE", False)
    monkeypatch.setattr(
        risk_manager,
        "get_loss_limits_status",
        lambda **_kwargs: _daily_loss_status(
            daily_loss=95.0,
            daily_used=9.5,
        ),
    )

    lot, _raw_lot, adjustments = risk_manager.calculate_smart_lot(
        balance=1000.0,
        risk_percent=1.5,
        sl_dist=10.0,
        market_regime="TRENDING",
        exec_grade="A",
    )

    assert 0 < lot <= 0.05
    assert any(item.startswith("DAILY_LOSS_BUDGET_CAP:") for item in adjustments)


def test_cooldown_does_not_return_an_executable_minimum_lot(monkeypatch):
    monkeypatch.setattr(risk_manager, "cooldown_active", lambda: True)

    lot, _raw_lot, adjustments = risk_manager.calculate_smart_lot(
        balance=1000.0,
        risk_percent=0.5,
        sl_dist=10.0,
    )

    assert lot == 0.0
    assert "COOLDOWN_ACTIVE" in adjustments
