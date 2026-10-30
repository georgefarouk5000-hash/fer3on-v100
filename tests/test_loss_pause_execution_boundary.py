import main


def test_two_losses_are_delivered_without_breakeven_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "register_loss_pause_result", lambda **kwargs: calls.append(kwargs))
    main._register_confirmed_close_events({
        "close_events": [
            {"ticket": 1, "profit": -10, "result": "LOSS"},
            {"ticket": 2, "profit": -10, "result": "LOSS"},
            {"ticket": 3, "profit": 0, "result": "BREAKEVEN"},
        ]
    })
    assert [call["trade_result"] for call in calls] == ["LOSS", "LOSS"]


def test_guard_does_not_bypass_pause_for_unlisted_regime(tmp_path, monkeypatch):
    import core.loss_pause_guard as guard
    monkeypatch.setattr(guard, "_STATE_PATH", str(tmp_path / "guard.json"))
    monkeypatch.setattr(guard, "LOSS_PAUSE_TRIGGER", 2)
    monkeypatch.setattr(guard, "LOSS_PAUSE_REQUIRE_REGIME", ("TRENDING",))
    guard.register_trade_result("LOSS", ticket=1, profit=-5)
    guard.register_trade_result("LOSS", ticket=2, profit=-5)
    result = guard.evaluate_loss_pause({"structure_analysis": {"choch": "NONE", "bos": "NONE"}}, "RANGING")
    assert result["trading_allowed"] is False