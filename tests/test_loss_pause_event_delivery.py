import main


def test_all_confirmed_final_close_events_are_delivered(monkeypatch):
    calls = []

    def record(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(main, "register_loss_pause_result", record)
    main._register_confirmed_close_events({
        "close_events": [
            {"ticket": 101, "deal_ticket": 201, "profit": -7.5, "result": "LOSS"},
            {"ticket": 102, "deal_ticket": 202, "profit": -8.0, "result": "LOSS"},
            {"ticket": 103, "deal_ticket": 203, "profit": 0.0, "result": "BREAKEVEN"},
        ]
    })
    assert [call["ticket"] for call in calls] == [101, 102]
    assert [call["trade_result"] for call in calls] == ["LOSS", "LOSS"]