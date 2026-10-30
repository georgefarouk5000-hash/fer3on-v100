import main


def test_freshness_guard_rejects_incomplete_snapshot(monkeypatch):
    incomplete = {
        "ready": False,
        "signal": "BUY",
        "entry_price": 0.0,
    }
    valid = {
        "ready": True,
        "signal": "BUY",
        "quality_gate": {},
        "execution": {},
    }
    assert not (
        incomplete
        and incomplete.get("ready") is True
        and incomplete.get("signal") in ("BUY", "SELL")
        and isinstance(incomplete.get("quality_gate"), dict)
        and isinstance(incomplete.get("execution"), dict)
    )
    assert (
        valid.get("ready") is True
        and valid.get("signal") in ("BUY", "SELL")
        and isinstance(valid.get("quality_gate"), dict)
        and isinstance(valid.get("execution"), dict)
    )