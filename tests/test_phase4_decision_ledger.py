"""PHASE 4 — Decision Ledger + Truth Attribution tests."""
import core.decision_ledger as dl
import core.settings as settings


def _tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DECISION_LEDGER_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "DECISION_LEDGER_LOG_PATH",
                        str(tmp_path / "decisions.jsonl"), raising=False)
    monkeypatch.setattr(settings, "DECISION_LEDGER_OUTCOMES_PATH",
                        str(tmp_path / "outcomes.jsonl"), raising=False)
    monkeypatch.setattr(settings, "BUILD_ID", "TEST_BUILD_1", raising=False)


def test_log_decision_enriches_and_persists(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    ok = dl.log_decision({"signal_id": "s1", "strategy": "SMC",
                          "session": "LONDON", "regime": "TRENDING",
                          "stage": "ENTRY", "decision": "APPROVE"})
    assert ok is True
    recs = dl.get_ledger_records()
    assert len(recs) == 1
    r = recs[0]
    assert r["build_id"] == "TEST_BUILD_1"
    assert r["schema_version"] == dl.LEDGER_SCHEMA_VERSION
    assert r["mode"] == "SHADOW"
    assert "logged_at" in r


def test_disabled_is_noop(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "DECISION_LEDGER_ENABLED", False, raising=False)
    assert dl.log_decision({"signal_id": "x"}) is False
    assert dl.attach_outcome("x", {"result": "WIN"}) is False
    assert dl.get_ledger_records() == []


def test_attach_outcome_links_signal(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    dl.log_decision({"signal_id": "s9", "strategy": "SMC",
                     "session": "NY", "regime": "RANGING"})
    assert dl.attach_outcome("s9", {"result": "WIN", "pnl": 12.5,
                                    "mfe": 2.1, "mae": 0.4}) is True
    outs = dl.get_outcomes()
    assert outs[0]["signal_id"] == "s9"
    assert outs[0]["build_id_at_decision"] == "TEST_BUILD_1"


def test_truth_attribution_buckets(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    for i, res in enumerate(["WIN", "LOSS", "WIN"]):
        dl.log_decision({"signal_id": f"s{i}", "strategy": "SMC",
                         "session": "LONDON", "regime": "TRENDING"})
        dl.attach_outcome(f"s{i}", {"result": res,
                                   "pnl": 10 if res == "WIN" else -8,
                                   "mfe": 1.5, "mae": 0.5})
    stats = dl.truth_attribution_stats(min_samples=2)
    assert stats["total_outcomes"] == 3
    key = "SMC|LONDON|TRENDING|TEST_BUILD_1"
    b = stats["buckets"][key]
    assert b["n"] == 3 and b["wins"] == 2 and b["losses"] == 1
    assert b["insufficient"] is False
    assert abs(b["win_rate"] - 2 / 3) < 1e-3


def test_never_raises_on_garbage(monkeypatch, tmp_path):
    _tmp(monkeypatch, tmp_path)
    assert dl.log_decision(None) is False
    assert dl.attach_outcome("", None) is False
    # missing dir perms etc. must not propagate
    monkeypatch.setattr(settings, "DECISION_LEDGER_LOG_PATH",
                        "/nonexistent-deep/\x00bad/x.jsonl", raising=False)
    assert dl.log_decision({"signal_id": "z"}) is False
